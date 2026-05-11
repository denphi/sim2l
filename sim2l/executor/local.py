# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Local executor for Python functions"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import time
import sqlite3

from .base import Executor
from ..definition import SimulationDefinition
from ..definition.function_workflow import function_from_source
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
        """Check if cached result exists.

        Routes through the cache service when ``cache_service_url`` is set,
        otherwise falls back to the legacy in-DB cache table. Mirrors the
        behaviour of ``NotebookExecutor.check_cache``.
        """
        if not self.cache:
            return None

        validated_inputs = self.prepare_inputs(simulation, inputs)

        # SQUID ID is the deterministic cross-installation cache key when the
        # cache service is configured; sim_id-derived cache_key is the legacy
        # local-only key used by the in-DB cache table.
        squid_id = compute_squid_id(
            simtool_name=simulation.name,
            simtool_revision=simulation.version,
            inputs=validated_inputs,
        )

        config = get_config()
        if getattr(config, "cache_service_url", None):
            return self._check_cache_service(squid_id)

        # Local-only path: keyed by sim_id-derived cache_key for back-compat.
        from ..repository import SimulationRepository
        repo = SimulationRepository()
        sim_id = repo.get_simulation_id(simulation.name, simulation.version)
        if sim_id is None:
            return None
        cache_key = compute_cache_key(sim_id, validated_inputs)
        return self._check_cache_local(cache_key)

    def _check_cache_service(self, cache_key: str) -> Optional[ExecutionResult]:
        """Look up a cached result via the configured cache service."""
        try:
            from ..database import CacheClient
            config = get_config()
            cache_client = CacheClient(
                service_url=config.cache_service_url,
                session_id=getattr(config, "cache_session_id", None),
            )
            cached_data = cache_client.get(cache_key)
            if not cached_data:
                return None

            execution_id = cached_data.get("execution_id")
            if not execution_id:
                logger.warning(f"Cache hit missing execution_id: {cached_data}")
                return None

            from ..result import load_result
            result = load_result(execution_id)
            logger.info(f"CACHED. Fetching results from execution {execution_id[:8]}...")
            return result
        except Exception as exc:
            logger.warning(f"Cache service lookup failed (treating as miss): {exc}")
            return None

    def _check_cache_local(self, cache_key: str) -> Optional[ExecutionResult]:
        """Look up a cached result via the legacy in-DB cache table."""
        db_path = get_config().db_path
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT execution_id FROM cache WHERE cache_key = ?",
                (cache_key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            execution_id = row[0]
            cursor.execute(
                """
                UPDATE cache
                SET last_accessed = ?, access_count = access_count + 1
                WHERE cache_key = ?
                """,
                (datetime.now().isoformat(), cache_key),
            )
            conn.commit()

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
            func = function_from_source(simulation.workflow)

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

        # Mirror the result into whichever cache backend is configured so a
        # subsequent run with the same inputs can short-circuit via check_cache.
        if self.cache and result.status == "completed":
            self._store_cache(result, validated_inputs)

        return result

    def _store_cache(self, result: ExecutionResult, validated_inputs: Dict[str, Any]) -> None:
        """Store a completed result in the cache backend (service or local table).

        Mirrors ``NotebookExecutor._store_cache_service``; failures are logged
        but never raised — caching is a best-effort optimization.
        """
        config = get_config()
        try:
            if getattr(config, "cache_service_url", None):
                from ..database import CacheClient
                from ..utils.serialization import serialize_for_hashing
                import hashlib
                import json

                serializable_inputs = {
                    k: serialize_for_hashing(v) for k, v in validated_inputs.items()
                }
                input_hash = hashlib.sha256(
                    json.dumps(serializable_inputs, sort_keys=True, default=str).encode()
                ).hexdigest()

                # The cache service uses the SQUID ID as the cross-installation
                # key, matching `_check_cache_service` above.
                cache_client = CacheClient(
                    service_url=config.cache_service_url,
                    session_id=getattr(config, "cache_session_id", None),
                )
                ok = cache_client.set(
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
                        "executed_at": result.executed_at.isoformat() if hasattr(result, "executed_at") else None,
                        "duration_seconds": result.duration_seconds,
                        "executor_type": "local",
                    },
                )
                if not ok:
                    logger.debug("Cache service rejected set; continuing")
                return

            # Legacy local-only path: write into the in-DB cache table.
            if not result.cache_key:
                return
            db_path = config.db_path
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache (
                        cache_key, execution_id, last_accessed, access_count
                    ) VALUES (?, ?, ?, COALESCE(
                        (SELECT access_count FROM cache WHERE cache_key = ?), 0
                    ))
                    """,
                    (
                        result.cache_key,
                        result.execution_id,
                        datetime.now().isoformat(),
                        result.cache_key,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            # Never let cache persistence errors fail the execution.
            logger.warning(f"Failed to store cache entry: {exc}")

    def __repr__(self):
        return f"LocalExecutor(cache={self.cache})"
