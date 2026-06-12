# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Subprocess executor for source-backed Python function workflows.

THREAT MODEL — read before using
================================

``IsolatedFunctionExecutor`` (also exported as ``SubprocessFunctionExecutor``)
provides **process isolation, not code sandboxing**. The worker process runs
the submitted ``simulate()`` source with no allow-list — ``import os;
os.system(...)`` works. What this executor does buy you:

* The worker is a **separate Python interpreter**, so any state it corrupts
  (sys.modules, globals, file descriptors held open) does not affect the
  caller's process.
* The caller imposes a **timeout** via ``subprocess.run(timeout=...)``.
* On POSIX, an optional ``RLIMIT_AS`` cap bounds the worker's address space.

What it does NOT buy you:

* No filesystem, network, or syscall restrictions. The worker has the same
  privileges as the parent. A malicious workflow can read ``~/.ssh``, exfil
  data over the network, kill arbitrary processes the parent can kill, etc.
* No protection against forking children that survive the parent's timeout
  unless callers explicitly kill the worker's process group (see review
  item #S1 — fixed by ``start_new_session=True``).

The right tool for *code sandboxing* is something like nsjail, gVisor, or a
container with a seccomp profile. This executor is the appropriate boundary
when the source is operator-trusted but you want bounded resources and a
fresh interpreter; it is NOT appropriate as the only barrier against
attacker-controlled source.

Review item #S2 / #C2.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .base import Executor
from ..config import get_logger
from ..definition import SimulationDefinition
from ..result import ExecutionResult
from ..utils import compute_cache_key, compute_squid_id

logger = get_logger()


_WORKER = r"""
import json
import sys
import traceback
from pathlib import Path

from sim2l.definition.function_workflow import function_from_source


def _json_default(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


source_path, input_path, output_path = sys.argv[1:4]
try:
    func = function_from_source(Path(source_path).read_bytes())
    inputs = json.loads(Path(input_path).read_text(encoding="utf-8"))
    outputs = func(**inputs)
    if not isinstance(outputs, dict):
        raise ValueError(f"Function must return dict, got {type(outputs)}")
    Path(output_path).write_text(
        json.dumps({"ok": True, "outputs": outputs}, default=_json_default),
        encoding="utf-8",
    )
except Exception as exc:
    Path(output_path).write_text(
        json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}),
        encoding="utf-8",
    )
    raise
"""


class IsolatedFunctionExecutor(Executor):
    """Execute function workflow source in a child Python process."""

    def __init__(
        self,
        cache: bool = True,
        timeout_seconds: Optional[float] = None,
        memory_limit_mb: Optional[int] = None,
        save_result: bool = True,
    ):
        super().__init__(cache=cache)
        self.save_result = save_result
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("SIM2L_FUNCTION_EXEC_TIMEOUT", "30")
        )
        raw_memory = memory_limit_mb
        if raw_memory is None and os.getenv("SIM2L_FUNCTION_MEMORY_MB"):
            raw_memory = int(os.getenv("SIM2L_FUNCTION_MEMORY_MB", "0"))
        self.memory_limit_mb = raw_memory

    def check_cache(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
    ) -> Optional[ExecutionResult]:
        """Look up a cached result via the cache service when configured.

        Without a configured cache service we return ``None`` (the catalog
        is authoritative). With a service configured, we mirror
        ``LocalExecutor.check_cache``'s SQUID-keyed lookup so arc and other
        callers using this executor still benefit from cross-installation
        cache hits.
        """
        if not self.cache:
            return None
        from ..config import get_config
        config = get_config()
        if not getattr(config, "cache_service_url", None):
            return None

        validated_inputs = self.prepare_inputs(simulation, inputs)
        squid_id = compute_squid_id(
            simtool_name=simulation.name,
            simtool_revision=simulation.version,
            inputs=validated_inputs,
        )
        try:
            from ..database import CacheClient
            cache_client = CacheClient(
                service_url=config.cache_service_url,
                session_id=getattr(config, "cache_session_id", None),
            )
            cached = cache_client.get(squid_id)
            if not cached:
                return None
            execution_id = cached.get("execution_id")
            if not execution_id:
                return None
            # Fallback loader: a hit produced on *another* installation has
            # no local DB row — reconstruct it from the results service.
            from ..result import load_result_with_fallback
            result = load_result_with_fallback(execution_id)
            result.cache_hit = True
            logger.info(f"CACHED. Fetching results from execution {execution_id[:8]}...")
            return result
        except Exception as exc:
            logger.warning(f"Cache service lookup failed (treating as miss): {exc}")
            return None

    def execute(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
        run_name: Optional[str] = None,
    ) -> ExecutionResult:
        cached = self.check_cache(simulation, inputs)
        if cached is not None:
            return cached

        validated_inputs = self.prepare_inputs(simulation, inputs)

        from ..repository import SimulationRepository

        repo = SimulationRepository()
        sim_id = repo.get_simulation_id(simulation.name, simulation.version)
        squid_id = compute_squid_id(
            simtool_name=simulation.name,
            simtool_revision=simulation.version,
            inputs=validated_inputs,
        )
        cache_key = compute_cache_key(sim_id, validated_inputs) if sim_id else None

        result = ExecutionResult.create(
            simulation_id=sim_id or 0,
            simulation_name=simulation.name,
            simulation_version=simulation.version,
            inputs=validated_inputs,
            output_schema=simulation.outputs,
            executor_type="isolated-function",
            cache_key=cache_key,
            squid_id=squid_id,
        )

        if callable(simulation.workflow):
            workflow_bytes = simulation.get_workflow_bytes()
        elif isinstance(simulation.workflow, bytes):
            workflow_bytes = simulation.workflow
        elif isinstance(simulation.workflow, Path):
            workflow_bytes = simulation.workflow.read_bytes()
        else:
            raise ValueError(
                f"IsolatedFunctionExecutor requires function source bytes, got {type(simulation.workflow)}"
            )

        start_time = time.time()
        try:
            payload = self._run_worker(workflow_bytes, validated_inputs)
            if not payload.get("ok"):
                raise RuntimeError(payload.get("error") or "Function workflow failed")
            result.set_outputs(payload["outputs"])
            result.status = "completed"
            logger.info(
                "Isolated function execution completed in %.2fs",
                time.time() - start_time,
            )
        except Exception as exc:
            result.set_error(str(exc))
            logger.error("Isolated function execution failed: %s", exc)
        finally:
            result.duration_seconds = time.time() - start_time

        if self.save_result:
            result.save()
        if self.cache and result.status == "completed":
            self._store_cache_service(result, validated_inputs)
        return result

    def _store_cache_service(
        self,
        result: ExecutionResult,
        validated_inputs: Dict[str, Any],
    ) -> None:
        """Mirror a completed result into the cache service.

        Mirrors ``LocalExecutor._store_cache``; failures are warnings only,
        never raised — caching is best-effort.
        """
        from ..config import get_config
        config = get_config()
        if not getattr(config, "cache_service_url", None):
            return
        try:
            from ..database import CacheClient
            from ..utils.serialization import serialize_for_hashing
            import hashlib

            serializable_inputs = {
                k: serialize_for_hashing(v) for k, v in validated_inputs.items()
            }
            input_hash = hashlib.sha256(
                json.dumps(serializable_inputs, sort_keys=True, default=str).encode()
            ).hexdigest()

            cache_client = CacheClient(
                service_url=config.cache_service_url,
                session_id=getattr(config, "cache_session_id", None),
            )
            cache_client.set(
                cache_key=result.squid_id,
                simulation_id=result.simulation_id,
                simulation_name=result.simulation_name,
                simulation_version=result.simulation_version,
                execution_id=result.execution_id,
                squid_id=result.squid_id,
                input_hash=input_hash,
                run_db_path="",
                ttl_seconds=None,
                metadata={
                    "duration_seconds": result.duration_seconds,
                    "executor_type": "isolated-function",
                },
            )
        except Exception as exc:
            logger.warning(f"Failed to store cache entry: {exc}")

    def _run_worker(self, workflow_bytes: bytes, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from ..utils.serialization import serialize_for_hashing

        with tempfile.TemporaryDirectory(prefix="sim2l_function_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            source_path = tmp_dir / "workflow.py"
            input_path = tmp_dir / "inputs.json"
            output_path = tmp_dir / "outputs.json"
            source_path.write_bytes(workflow_bytes)
            # Use the shared serializer so numpy / Pint / datetime inputs
            # don't blow up at ``json.dumps`` time. Review item #S4.
            input_path.write_text(
                json.dumps(serialize_for_hashing(inputs)),
                encoding="utf-8",
            )

            # Build the preexec_fn so the child becomes a new process group
            # leader on POSIX. That gives us a kill target that covers any
            # descendants the workflow may spawn (review item #S1).
            limit_resources = self._limit_resources()

            def _setup_child():
                if os.name == "posix":
                    try:
                        os.setsid()
                    except OSError:
                        pass
                if limit_resources is not None:
                    limit_resources()

            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _WORKER,
                    str(source_path),
                    str(input_path),
                    str(output_path),
                ],
                cwd=tmp_dir,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=_setup_child if os.name == "posix" else None,
            )
            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                # Kill the whole process group so descendants the worker
                # spawned don't survive the parent's timeout.
                self._kill_process_tree(proc)
                stdout, stderr = proc.communicate()
                return {
                    "ok": False,
                    "error": f"workflow timed out after {self.timeout_seconds}s",
                }

            if output_path.exists():
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            else:
                payload = {
                    "ok": False,
                    "error": (stderr or "").strip() or (stdout or "").strip(),
                }
            if proc.returncode != 0 and payload.get("ok"):
                payload = {
                    "ok": False,
                    "error": (stderr or "").strip() or f"exit code {proc.returncode}",
                }
            return payload

    @staticmethod
    def _kill_process_tree(proc: subprocess.Popen) -> None:
        """Best-effort SIGKILL of the worker's process group, then process.

        Review item #T8: the previous implementation called ``os.getpgid``
        then ``os.killpg`` without checking whether the child was still
        alive in between. On POSIX, PIDs are recycled — if the child exited
        between the two calls and the kernel handed its PID to another
        process, we'd ``SIGKILL`` an unrelated process group.

        Mitigation:

        1. The child is started with ``os.setsid()`` (already in place at
           the spawn site), so its process group id equals its PID. We use
           ``proc.pid`` directly instead of ``os.getpgid`` — that removes
           one of the two race windows.
        2. ``proc.poll()`` is checked immediately before ``killpg`` so we
           don't send signals to a reaped child. There is still a brief
           window between ``poll()`` and ``killpg`` where the child could
           exit, but ``Popen.poll()`` reaps the process via ``waitpid``
           once it sees the exit — so after a successful ``poll()``
           returning non-None the PID stays reserved by Popen until
           ``wait()`` is called. The kernel won't recycle it.
        3. ``ProcessLookupError`` is tolerated so the kernel reusing the
           PID *after* this routine completes can't surface as an error.
        """
        import signal

        if os.name == "posix":
            # Skip the kill entirely if the child has already exited; the
            # subsequent communicate() will reap it. This both avoids the
            # PID-reuse window and is the documented safer pattern.
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    # Child exited between poll() and killpg(), or the
                    # caller doesn't have permission (which shouldn't
                    # happen for a child we spawned). Either way, the
                    # subsequent communicate() will reap it.
                    pass
        # Fallback / Windows path — kill the direct child. Popen.kill
        # already tolerates the "process gone" case quietly on 3.10+, but
        # we wrap in try/except for older patch levels.
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass

    def _limit_resources(self):
        if os.name != "posix" or not self.memory_limit_mb:
            return None

        def apply_limits():
            import resource

            memory_bytes = int(self.memory_limit_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

        return apply_limits

    def __repr__(self):
        return (
            "IsolatedFunctionExecutor("
            f"cache={self.cache}, timeout_seconds={self.timeout_seconds})"
        )


# Honest alias that matches the threat model described in the module
# docstring: this is process isolation, not code sandboxing. New callers
# should prefer the descriptive name; ``IsolatedFunctionExecutor`` stays
# as the back-compat export.
SubprocessFunctionExecutor = IsolatedFunctionExecutor
