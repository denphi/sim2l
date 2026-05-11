# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Subprocess executor for source-backed Python function workflows."""

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
        # Catalog-service execution is intentionally authoritative per request.
        return None

    def execute(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
        run_name: Optional[str] = None,
    ) -> ExecutionResult:
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
        return result

    def _run_worker(self, workflow_bytes: bytes, inputs: Dict[str, Any]) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="sim2l_function_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            source_path = tmp_dir / "workflow.py"
            input_path = tmp_dir / "inputs.json"
            output_path = tmp_dir / "outputs.json"
            source_path.write_bytes(workflow_bytes)
            input_path.write_text(json.dumps(inputs), encoding="utf-8")

            completed = subprocess.run(
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
                capture_output=True,
                timeout=self.timeout_seconds,
                preexec_fn=self._limit_resources(),
            )

            if output_path.exists():
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            else:
                payload = {
                    "ok": False,
                    "error": completed.stderr.strip() or completed.stdout.strip(),
                }
            if completed.returncode != 0 and payload.get("ok"):
                payload = {
                    "ok": False,
                    "error": completed.stderr.strip() or f"exit code {completed.returncode}",
                }
            return payload

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
