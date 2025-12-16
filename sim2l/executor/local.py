"""Local executor for Python functions"""

import uuid
import pickle
from typing import Dict, Any, Optional
from datetime import datetime
import time
import sqlite3

from .base import Executor
from ..definition import SimulationDefinition
from ..result import ExecutionResult
from ..utils import compute_squid_id, compute_cache_key
from ..config import get_config, get_logger

logger = get_logger()


class LocalExecutor(Executor):
    """Execute simulations as Python functions in-process

    This executor runs Python functions directly without notebooks.
    """

    def __init__(self, cache: bool = True):
        """Initialize LocalExecutor

        Args:
            cache: Enable caching
        """
        super().__init__(cache=cache)

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
        """Execute simulation function locally

        Args:
            simulation: Simulation definition
            inputs: Input parameters
            run_name: Optional run name (unused for local execution)

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

        logger.info(f"Executing {simulation.name} v{simulation.version} locally")

        # Get function from workflow
        if callable(simulation.workflow):
            func = simulation.workflow
        else:
            # Deserialize pickled function
            func = pickle.loads(simulation.workflow)

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
            executor_type="local",
            cache_key=cache_key,
            squid_id=squid_id,
        )

        # Execute function
        start_time = time.time()

        try:
            # Call function with inputs
            output_data = func(**validated_inputs)

            # Calculate duration
            duration = time.time() - start_time
            result.duration_seconds = duration

            # Validate outputs
            if not isinstance(output_data, dict):
                raise ValueError(
                    f"Function must return dict, got {type(output_data)}"
                )

            # Set outputs
            result.set_outputs(output_data)
            result.status = "completed"

            logger.info(f"Execution completed in {duration:.2f}s")

        except Exception as e:
            duration = time.time() - start_time
            result.duration_seconds = duration
            result.set_error(str(e))
            logger.error(f"Execution failed: {e}")

        # Save result to database
        result.save()

        return result

    def __repr__(self):
        return f"LocalExecutor(cache={self.cache})"
