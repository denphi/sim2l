"""
Mixin for executors to enable run database integration.

This mixin adds run database creation and management to executors.
"""

import os
import logging
import platform
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from ..config import get_config
from ..database import RunDatabase

logger = logging.getLogger(__name__)


class RunDatabaseMixin:
    """
    Mixin to add run database support to executors.

    When mixed into an Executor class, automatically creates and manages
    per-run SQLite databases.
    """

    def _create_run_database(
        self,
        execution_id: str,
        simulation_name: str,
        simulation_version: str,
        simulation_id: Optional[int] = None,
        squid_id: Optional[str] = None,
        executor_type: str = "local",
        executor_config: Optional[Dict[str, Any]] = None,
        cache_key: Optional[str] = None,
        cache_hit: bool = False,
    ) -> Optional[RunDatabase]:
        """
        Create a run database for this execution.

        Args:
            execution_id: Unique execution ID
            simulation_name: Simulation name
            simulation_version: Simulation version
            simulation_id: Simulation ID from repository
            squid_id: SQUID ID
            executor_type: Type of executor (local, notebook, etc.)
            executor_config: Executor configuration
            cache_key: Cache key if caching enabled
            cache_hit: Whether this is a cache hit

        Returns:
            RunDatabase instance or None if disabled
        """
        config = get_config()

        if not config.use_run_database:
            return None

        try:
            # Get session info if available
            session_id = config.catalog_session_id or config.cache_session_id
            user_id = os.environ.get("USER") or os.environ.get("USERNAME")

            # Create run database
            run_db = RunDatabase(
                execution_id=execution_id,
                db_path=self._get_run_db_path(execution_id),
            )

            # Gather environment info
            environment = {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": platform.system(),
                "platform_version": platform.version(),
                "hostname": platform.node(),
                "cwd": os.getcwd(),
            }

            # Initialize run metadata
            run_db.initialize_run(
                simulation_name=simulation_name,
                simulation_version=simulation_version,
                simulation_id=simulation_id,
                squid_id=squid_id,
                executor_type=executor_type,
                executor_config=executor_config,
                user_id=user_id,
                session_id=session_id,
                environment=environment,
                cache_key=cache_key,
                cache_hit=cache_hit,
            )

            logger.info(f"Created run database: {run_db.db_path}")
            return run_db

        except Exception as e:
            logger.error(f"Failed to create run database: {e}")
            return None

    def _get_run_db_path(self, execution_id: str) -> str:
        """Get the path for a run database."""
        config = get_config()

        if config.run_db_base_path:
            base_path = Path(config.run_db_base_path)
        else:
            base_path = Path.home() / ".sim2l" / "runs"

        base_path.mkdir(parents=True, exist_ok=True)
        return str(base_path / f"{execution_id}.db")

    def _save_inputs_to_run_db(
        self, run_db: Optional[RunDatabase], inputs: Dict[str, Any], schema
    ):
        """Save inputs to run database."""
        if not run_db:
            return

        try:
            for name, value in inputs.items():
                # Get field info from schema
                field = schema.fields.get(name)
                if field:
                    field_type = field.__class__.__name__
                    units = getattr(field, "units", None)
                else:
                    field_type = type(value).__name__
                    units = None

                run_db.save_input(
                    name=name, value=value, field_type=field_type, units=units
                )

            logger.debug(f"Saved {len(inputs)} inputs to run database")

        except Exception as e:
            logger.error(f"Failed to save inputs to run database: {e}")

    def _save_outputs_to_run_db(
        self, run_db: Optional[RunDatabase], outputs: Dict[str, Any], schema
    ):
        """Save outputs to run database."""
        if not run_db:
            return

        try:
            for name, value in outputs.items():
                # Get field info from schema
                field = schema.fields.get(name)
                if field:
                    field_type = field.__class__.__name__
                    units = getattr(field, "units", None)
                else:
                    field_type = type(value).__name__
                    units = None

                run_db.save_output(
                    name=name, value=value, field_type=field_type, units=units
                )

            logger.debug(f"Saved {len(outputs)} outputs to run database")

        except Exception as e:
            logger.error(f"Failed to save outputs to run database: {e}")

    def _complete_run_db(
        self,
        run_db: Optional[RunDatabase],
        status: str,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        error_traceback: Optional[str] = None,
    ):
        """Mark run database as completed."""
        if not run_db:
            return

        try:
            run_db.complete_run(
                status=status,
                duration_seconds=duration_seconds,
                error_message=error_message,
                error_traceback=error_traceback,
            )
            logger.info(
                f"Completed run database with status: {status} "
                f"(size: {run_db.get_size_bytes() / 1024:.1f} KB)"
            )

        except Exception as e:
            logger.error(f"Failed to complete run database: {e}")

    def _log_to_run_db(
        self,
        run_db: Optional[RunDatabase],
        level: str,
        message: str,
        logger_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None,
    ):
        """Log a message to run database."""
        if not run_db:
            return

        try:
            import traceback

            exception_type = None
            exception_message = None
            stack_trace = None

            if exception:
                exception_type = exception.__class__.__name__
                exception_message = str(exception)
                stack_trace = "".join(
                    traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                )

            run_db.log(
                level=level,
                message=message,
                logger_name=logger_name,
                context=context,
                exception_type=exception_type,
                exception_message=exception_message,
                stack_trace=stack_trace,
            )

        except Exception as e:
            logger.error(f"Failed to log to run database: {e}")

    def _save_artifact_to_run_db(
        self,
        run_db: Optional[RunDatabase],
        name: str,
        path: Optional[str] = None,
        content: Optional[bytes] = None,
        content_type: Optional[str] = None,
        category: str = "output",
        description: Optional[str] = None,
    ):
        """Save an artifact to run database."""
        if not run_db:
            return

        try:
            artifact_id = run_db.save_artifact(
                name=name,
                path=path,
                content=content,
                content_type=content_type,
                category=category,
                description=description,
            )

            logger.debug(f"Saved artifact {name} to run database (ID: {artifact_id})")
            return artifact_id

        except Exception as e:
            logger.error(f"Failed to save artifact to run database: {e}")
            return None
