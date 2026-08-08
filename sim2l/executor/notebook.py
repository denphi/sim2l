# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Notebook executor using Papermill"""

import os
import uuid
import tempfile
import threading
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import time
import sqlite3
import json

import papermill as pm

from .base import Executor
from ..definition import SimulationDefinition
from ..result import ExecutionResult
from ..utils import compute_squid_id
from ..utils.serialization import serialize_output_value as _to_value
from ..config import get_config, get_logger

logger = get_logger()


# The identity of a run reaches the notebook through process-global environment
# variables: the kernel Papermill spawns inherits ``os.environ``, and
# ``sim2l.api.save_outputs`` reads ``SIM2L_EXECUTION_ID`` / ``SIM2L_DB_PATH``
# from inside that kernel to decide which execution its outputs belong to.
#
# ``os.environ`` is process-wide, and the Flask services run threaded
# (``Flask.run`` defaults ``threaded=True``). Two overlapping executions used to
# overwrite each other's values between the set and the kernel spawn, so results
# were written under whichever execution_id happened to be current — silently,
# with no error and no way to tell afterwards which runs were misfiled.
#
# This lock serializes the set → spawn → restore window. It does mean notebook
# executions do not overlap within a process, which is a real throughput cost on
# long simulations; correctness of the provenance record wins. The lock could be
# released right after the kernel starts, but Papermill exposes no hook there.
# The lasting fix is to stop routing per-run identity through the environment —
# inject it at kernel launch, or pass it to ``save_outputs`` explicitly — which
# is a change to the notebook-facing contract and belongs in its own release.
_EXECUTION_ENV_LOCK = threading.Lock()


@contextmanager
def _execution_environment(values: Dict[str, str]):
    """Hold ``values`` in ``os.environ`` for the duration of the block.

    Serialized against other executions in this process, and restores the
    previous values (rather than deleting) on the way out, so a caller that had
    these set for its own reasons gets them back. The restore runs even when the
    body raises — the old code cleared them on the success path only, so a
    notebook that failed left its execution id set for whatever ran next.
    """
    with _EXECUTION_ENV_LOCK:
        previous = {key: os.environ.get(key) for key in values}
        os.environ.update(values)
        try:
            yield
        finally:
            for key, was in previous.items():
                if was is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = was


def _notebook_timeouts() -> Dict[str, Any]:
    """Execution/startup timeouts for Papermill, in seconds.

    Mirrors ``SIM2L_FUNCTION_EXEC_TIMEOUT`` on the function executor so both
    execution paths reachable from ``/simulations/<id>/execute`` are bounded.
    Without this a notebook that loops forever, blocks on input, or stalls on a
    network read held its worker thread indefinitely.

    ``SIM2L_NOTEBOOK_EXEC_TIMEOUT=0`` disables the execution cap for the genuinely
    long-running solves this library exists to run; startup stays bounded.
    """
    raw = os.getenv("SIM2L_NOTEBOOK_EXEC_TIMEOUT", "3600")
    try:
        execution_timeout: Optional[float] = float(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid SIM2L_NOTEBOOK_EXEC_TIMEOUT=%r; using 3600s", raw)
        execution_timeout = 3600.0
    if execution_timeout is not None and execution_timeout <= 0:
        execution_timeout = None  # explicitly unbounded

    try:
        start_timeout = float(os.getenv("SIM2L_NOTEBOOK_START_TIMEOUT", "60"))
    except (TypeError, ValueError):
        start_timeout = 60.0

    return {"execution_timeout": execution_timeout, "start_timeout": start_timeout}


class NotebookExecutor(Executor):
    """Execute simulations using Papermill

    This executor runs Jupyter notebooks using Papermill, similar to
    simtool's LocalRun class.
    """

    def __init__(
        self,
        cache: bool = True,
        output_dir: Optional[Path] = None,
        copy_files: bool = True,
        register_results: bool = None,
    ):
        """Initialize NotebookExecutor

        Args:
            cache: Enable caching
            output_dir: Output directory (uses temp if None)
            copy_files: Copy supporting files to output directory
            register_results: Register results with results service (default: from config)
        """
        super().__init__(cache=cache, output_dir=output_dir)
        self.copy_files = copy_files

        # Check if results registration should be enabled
        # Use parameter if provided, otherwise check config
        if register_results is None:
            config = get_config()
            # Enable if results service URL is configured or results database exists
            self.register_results = (
                hasattr(config, 'results_service_url') and config.results_service_url is not None
            ) or (Path.home() / ".sim2l" / "results.db").exists()
        else:
            self.register_results = register_results

    def check_cache(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
    ) -> Optional[ExecutionResult]:
        """Check if cached result exists

        Args:
            simulation: Simulation definition
            inputs: Input parameters

        Returns:
            Cached ExecutionResult or None
        """
        if not self.cache:
            logger.debug("Cache is disabled, skipping cache check")
            return None

        # Prepare/validate inputs to match what will be used in execution
        validated_inputs = self.prepare_inputs(simulation, inputs)

        # Compute SQUID ID (deterministic cache key)
        squid_id = compute_squid_id(
            simtool_name=simulation.name,
            simtool_revision=simulation.version,
            inputs=validated_inputs
        )
        logger.debug(f"Computed SQUID ID for cache lookup: {squid_id}")

        # Check if cache service is configured
        config = get_config()
        logger.debug(f"Cache service URL: {getattr(config, 'cache_service_url', 'NOT SET')}")
        if hasattr(config, 'cache_service_url') and config.cache_service_url:
            # Use cache service with SQUID ID as cache key
            logger.debug(f"Using cache service at {config.cache_service_url}")
            return self._check_cache_service(squid_id)
        else:
            # Use local SQLite cache with SQUID ID as cache key
            logger.debug("Using local SQLite cache")
            return self._check_cache_local(squid_id)

    def _check_cache_service(self, cache_key: str) -> Optional[ExecutionResult]:
        """Check cache service for cached result"""
        try:
            from ..database import CacheClient
            config = get_config()

            logger.debug(f"Checking cache service for key: {cache_key}")
            # Pass the cache session id (like the local/isolated executors)
            # so a require_auth cache service accepts the lookup instead of
            # turning every notebook run into a silent permanent miss.
            cache_client = CacheClient(
                service_url=config.cache_service_url,
                session_id=getattr(config, "cache_session_id", None),
            )
            cached_data = cache_client.get(cache_key)

            if cached_data is None:
                logger.debug(f"Cache miss for key: {cache_key}")
                return None

            logger.debug(f"Cache hit for key: {cache_key}, data: {cached_data}")
            # Load execution result from cached data
            execution_id = cached_data.get('execution_id')
            if execution_id:
                # Fallback loader: a hit produced on *another* installation
                # has no local DB row — reconstruct from the results service.
                from ..result import load_result_with_fallback
                logger.debug(f"Loading cached result from execution: {execution_id}")
                result = load_result_with_fallback(execution_id)
                result.cache_hit = True
                logger.info(f"CACHED. Fetching results from execution {execution_id[:8]}...")
                return result

            logger.warning(f"Cache data missing execution_id: {cached_data}")
            return None

        except Exception as e:
            logger.warning(f"Failed to check cache service: {e}", exc_info=True)
            return None

    def _check_cache_local(self, cache_key: str) -> Optional[ExecutionResult]:
        """Check local SQLite cache for cached result"""
        db_path = get_config().db_path
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT execution_id FROM cache WHERE cache_key = ?
            """, (cache_key,))

            row = cursor.fetchone()

            if row is None:
                return None

            execution_id = row[0]

            # Update cache access
            cursor.execute("""
                UPDATE cache
                SET last_accessed = ?, access_count = access_count + 1
                WHERE cache_key = ?
            """, (datetime.now().isoformat(), cache_key))

            conn.commit()

            # Load execution result
            from ..result import load_result
            result = load_result(execution_id)
            result.cache_hit = True

            logger.info(f"CACHED. Fetching results from execution {execution_id[:8]}...")

            return result

        finally:
            conn.close()

    def execute(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
        run_name: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute simulation notebook using Papermill

        Args:
            simulation: Simulation definition
            inputs: Input parameters
            run_name: Optional run name

        Returns:
            ExecutionResult

        Raises:
            ExecutionError: If execution fails
        """
        # Check cache first
        cached_result = self.check_cache(simulation, inputs)
        if cached_result is not None:
            return cached_result

        # Prepare inputs
        validated_inputs = self.prepare_inputs(simulation, inputs)

        # Generate run name
        if run_name is None:
            run_name = str(uuid.uuid4()).replace('-', '')

        # Create output directory
        if self.output_dir:
            outdir = Path(self.output_dir) / run_name
        else:
            outdir = Path(tempfile.gettempdir()) / "sim2l_runs" / run_name

        outdir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Executing {simulation.name} v{simulation.version} in {outdir}")

        # Write notebook to temporary file
        notebook_path = outdir / f"{simulation.name}.ipynb"
        with open(notebook_path, 'wb') as f:
            f.write(simulation.workflow)

        # Output notebook path
        output_notebook = outdir / f"{simulation.name}_output.ipynb"

        # Get simulation DB ID
        from ..repository import SimulationRepository
        repo = SimulationRepository()
        sim_id = repo.get_simulation_id(simulation.name, simulation.version)

        # Compute SQUID ID (also used as cache key for deterministic caching)
        squid_id = compute_squid_id(
            simtool_name=simulation.name,
            simtool_revision=simulation.version,
            inputs=validated_inputs
        )

        # Use SQUID ID as cache key (deterministic based on simulation + inputs)
        cache_key = squid_id

        # Create execution result
        result = ExecutionResult.create(
            simulation_id=sim_id or 0,
            simulation_name=simulation.name,
            simulation_version=simulation.version,
            inputs=validated_inputs,
            output_schema=simulation.outputs,
            executor_type="notebook",
            cache_key=cache_key,
            squid_id=squid_id,
        )

        # Execute notebook
        start_time = time.time()

        try:
            # Convert Pint Quantity objects to plain values for Papermill
            papermill_params = {}
            for key, value in validated_inputs.items():
                if hasattr(value, 'magnitude'):
                    # Extract magnitude from Pint Quantity
                    papermill_params[key] = value.magnitude
                else:
                    papermill_params[key] = value

            # Set environment variables for save_outputs()
            from ..config import get_config

            # Convert DB path to absolute path
            db_path = Path(get_config().db_path).resolve()

            # The kernel Papermill spawns inherits os.environ, which is how
            # save_outputs() learns which execution it is writing for. That
            # window is serialized and restored by _execution_environment —
            # see the comment on _EXECUTION_ENV_LOCK for why.
            timeouts = _notebook_timeouts()
            with _execution_environment({
                'SIM2L_EXECUTION_ID': result.execution_id,
                'SIM2L_SQUID_ID': squid_id,
                'SIM2L_DB_PATH': str(db_path),
            }):
                pm.execute_notebook(
                    input_path=str(notebook_path),
                    output_path=str(output_notebook),
                    parameters=papermill_params,
                    cwd=str(outdir),
                    start_timeout=timeouts["start_timeout"],
                    # Forwarded to nbclient as a per-cell execution cap.
                    execution_timeout=timeouts["execution_timeout"],
                )

            # Calculate duration
            duration = time.time() - start_time
            result.duration_seconds = duration

            # Extract outputs from executed notebook
            outputs = self._extract_outputs(output_notebook, simulation.outputs, result.execution_id)
            result.set_outputs(outputs)

            result.status = "completed"

            logger.info(f"Execution completed in {duration:.2f}s")

        except Exception as e:
            duration = time.time() - start_time
            result.duration_seconds = duration
            result.set_error(str(e))
            logger.error(f"Execution failed: {e}")

        # Save result to database
        result.save()

        # Store in cache service if configured and execution successful
        if self.cache and result.status == "completed" and result.cache_key:
            config = get_config()
            if hasattr(config, 'cache_service_url') and config.cache_service_url:
                self._store_cache_service(result)

        # Register with results service if enabled
        if self.register_results and result.status == "completed":
            self._register_result(result, simulation, validated_inputs)

        return result

    def _extract_outputs(
        self,
        notebook_path: Path,
        output_schema,
        execution_id: str = None
    ) -> Dict[str, Any]:
        """Extract outputs from executed notebook

        Reads outputs from database (saved by save_outputs() in notebook).
        Falls back to scrapbook for backward compatibility.

        Args:
            notebook_path: Path to executed notebook
            output_schema: Output schema
            execution_id: Execution ID to read outputs for

        Returns:
            Dictionary of output values
        """
        outputs = {}

        # Try to read from database first (saved by save_outputs())
        if execution_id:
            try:
                import sqlite3
                from ..config import get_config
                from ..utils.serialization import deserialize_value

                db_path = get_config().db_path
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Read outputs from database
                cursor.execute("""
                    SELECT name, value
                    FROM outputs
                    WHERE execution_id = ?
                """, (execution_id,))

                for name, value_json in cursor.fetchall():
                    if name in output_schema.keys():
                        try:
                            outputs[name] = deserialize_value(value_json)
                        except Exception as e:
                            logger.warning(f"Failed to deserialize output '{name}': {e}")

                conn.close()

                # If we got outputs from database, return them
                if outputs:
                    logger.info(f"Extracted {len(outputs)} outputs from database")
                    return outputs

            except Exception as e:
                logger.warning(f"Failed to read outputs from database: {e}")

        # Fall back to scrapbook
        try:
            import scrapbook as sb

            # Read notebook with scrapbook
            nb = sb.read_notebook(str(notebook_path))

            # Extract each output from schema
            for name in output_schema.keys():
                try:
                    # Try to get scraped data
                    value = nb.scraps[name].data
                    outputs[name] = value
                except (KeyError, AttributeError):
                    # Output not found
                    logger.warning(f"Output '{name}' not found in notebook")

        except Exception as e:
            logger.error(f"Failed to extract outputs from scrapbook: {e}")

        return outputs

    def _store_cache_service(self, result: ExecutionResult):
        """Store result in cache service

        Args:
            result: Execution result to cache
        """
        try:
            from ..database import CacheClient
            import hashlib
            import json
            import numpy as np
            config = get_config()

            cache_client = CacheClient(
                service_url=config.cache_service_url,
                session_id=getattr(config, "cache_session_id", None),
            )

            # Convert inputs to JSON-serializable format (extract magnitudes from Pint Quantities)
            serializable_inputs = {}
            for key, value in result.inputs.items():
                if hasattr(value, 'magnitude'):
                    # Extract magnitude from Pint Quantity
                    serializable_inputs[key] = value.magnitude
                elif isinstance(value, np.ndarray):
                    # Convert numpy arrays to lists
                    serializable_inputs[key] = value.tolist()
                elif isinstance(value, (np.integer, np.floating)):
                    # Convert numpy scalars to Python types
                    serializable_inputs[key] = value.item()
                else:
                    serializable_inputs[key] = value

            # Compute input hash for cache entry
            input_hash = hashlib.sha256(
                json.dumps(serializable_inputs, sort_keys=True).encode()
            ).hexdigest()

            # Store cache entry with all required parameters
            success = cache_client.set(
                cache_key=result.cache_key,
                simulation_id=result.simulation_id,
                simulation_name=result.simulation_name,
                simulation_version=result.simulation_version,
                execution_id=result.execution_id,
                squid_id=result.squid_id,
                input_hash=input_hash,
                run_db_path='',  # NotebookExecutor doesn't use per-run databases
                ttl_seconds=None,  # No expiration
                metadata={
                    'executed_at': result.executed_at.isoformat(),
                    'duration_seconds': result.duration_seconds
                }
            )

            if success:
                logger.debug(f"Stored result in cache service: {result.cache_key[:40]}...")
            else:
                logger.warning(f"Failed to store result in cache service")

        except Exception as e:
            logger.warning(f"Failed to store result in cache service: {e}")

    def _register_result(
        self,
        result: ExecutionResult,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any]
    ):
        """Register execution result with results service

        Args:
            result: Execution result to register
            simulation: Simulation definition
            inputs: Input parameters
        """
        try:
            from ..config import get_config
            config = get_config()

            # Check if results service is configured
            if hasattr(config, 'results_service_url') and config.results_service_url:
                # Use results service API
                self._register_result_via_api(result, simulation, inputs)
            else:
                # Fall back to local SQLite registration
                self._register_result_local(result, simulation, inputs)

        except Exception as e:
            logger.warning(f"Failed to register result with results service: {e}")

    def _register_result_via_api(
        self,
        result: ExecutionResult,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any]
    ):
        """Register result via results service API

        Args:
            result: Execution result to register
            simulation: Simulation definition
            inputs: Input parameters
        """
        import requests
        import json
        from ..config import get_config

        config = get_config()

        # Serialize outputs and inputs using the shared helper
        outputs_dict = {}
        if result.outputs:
            for key, value in result.outputs.to_dict().items():
                outputs_dict[key] = _to_value(value)

        inputs_dict = {}
        for key, value in inputs.items():
            inputs_dict[key] = _to_value(value)

        response = requests.post(
            f"{config.results_service_url.rstrip('/')}/register_direct",
            json={
                'execution_id': result.execution_id,
                'simulation_name': simulation.name,
                'simulation_version': simulation.version,
                'squid_id': result.squid_id,
                'input_params': inputs_dict,
                'output_params': outputs_dict,
                'status': result.status,
                'duration_seconds': result.duration_seconds,
                'run_db_path': ''
            },
            headers={'Content-Type': 'application/json'},
            timeout=10
        )

        if response.status_code == 200:
            logger.debug(f"Registered result {result.squid_id[:40]}... via API")
        else:
            logger.warning(f"Failed to register result via API: {response.status_code} {response.text}")

    def _register_result_local(
        self,
        result: ExecutionResult,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any]
    ):
        """Register result to local SQLite database

        Args:
            result: Execution result to register
            simulation: Simulation definition
            inputs: Input parameters
        """
        import sqlite3
        import json

        # Get results database path
        results_db_path = Path.home() / ".sim2l" / "results.db"

        if not results_db_path.exists():
            logger.debug("Results database not found, skipping registration")
            return

        # Serialize outputs and inputs using the shared helper
        outputs_dict = {}
        if result.outputs:
            for key, value in result.outputs.to_dict().items():
                outputs_dict[key] = _to_value(value)

        inputs_dict = {}
        for key, value in inputs.items():
            inputs_dict[key] = _to_value(value)

        # Insert into results database
        conn = sqlite3.connect(str(results_db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO execution_results (
                execution_id, simulation_name, simulation_version, squid_id,
                input_params, output_params, status, duration_seconds,
                run_db_path, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            result.squid_id,
            simulation.name,
            simulation.version,
            result.squid_id,
            json.dumps(inputs_dict),
            json.dumps(outputs_dict),
            result.status,
            result.duration_seconds,
            ''  # No run database in notebook executor
        ))

        conn.commit()
        conn.close()

        logger.debug(f"Registered result {result.squid_id[:40]}... to local database")

    def __repr__(self):
        return f"NotebookExecutor(cache={self.cache}, copy_files={self.copy_files}, register_results={self.register_results})"
