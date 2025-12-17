"""Notebook executor using Papermill"""

import os
import uuid
import tempfile
import shutil
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
from ..utils import compute_squid_id, compute_cache_key
from ..config import get_config, get_logger

logger = get_logger()


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
            return None

        # Get simulation DB ID
        from ..repository import SimulationRepository
        repo = SimulationRepository()
        sim_id = repo.get_simulation_id(simulation.name, simulation.version)

        if sim_id is None:
            return None

        # Compute cache key
        cache_key = compute_cache_key(sim_id, inputs)

        # Check cache table
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

        # Compute SQUID ID
        squid_id = compute_squid_id(
            simtool_name=simulation.name,
            simtool_revision=simulation.version,
            inputs=validated_inputs
        )

        # Compute cache key
        cache_key = compute_cache_key(sim_id, validated_inputs) if sim_id else None

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

            os.environ['SIM2L_EXECUTION_ID'] = result.execution_id
            os.environ['SIM2L_SQUID_ID'] = squid_id
            os.environ['SIM2L_DB_PATH'] = str(db_path)

            # Execute with Papermill
            pm.execute_notebook(
                input_path=str(notebook_path),
                output_path=str(output_notebook),
                parameters=papermill_params,
                cwd=str(outdir),
            )

            # Clean up environment variables
            os.environ.pop('SIM2L_EXECUTION_ID', None)
            os.environ.pop('SIM2L_SQUID_ID', None)
            os.environ.pop('SIM2L_DB_PATH', None)

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
            import sqlite3
            import json

            # Get results database path
            results_db_path = Path.home() / ".sim2l" / "results.db"

            if not results_db_path.exists():
                logger.debug("Results database not found, skipping registration")
                return

            # Convert outputs to serializable format (handle Pint quantities and numpy arrays)
            def to_value(val):
                """Extract numeric value from Pint quantity, numpy array, or return as-is"""
                import numpy as np

                # Handle Pint quantities
                if hasattr(val, 'magnitude'):
                    val = val.magnitude

                # Handle numpy arrays
                if isinstance(val, np.ndarray):
                    return val.tolist()

                # Handle numpy scalars
                if isinstance(val, (np.integer, np.floating)):
                    return val.item()

                # Handle regular numbers
                if isinstance(val, (int, float)):
                    return float(val)

                # Handle strings and booleans
                if isinstance(val, (str, bool)):
                    return val

                # For anything else, try to convert to string
                return str(val)

            # Serialize outputs
            outputs_dict = {}
            if result.outputs:
                # Use to_dict() to get the raw output data
                for key, value in result.outputs.to_dict().items():
                    outputs_dict[key] = to_value(value)

            # Serialize inputs
            inputs_dict = {}
            for key, value in inputs.items():
                inputs_dict[key] = to_value(value)

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

            logger.debug(f"Registered result {result.squid_id[:40]}... with results service")

        except Exception as e:
            logger.warning(f"Failed to register result with results service: {e}")

    def __repr__(self):
        return f"NotebookExecutor(cache={self.cache}, copy_files={self.copy_files}, register_results={self.register_results})"
