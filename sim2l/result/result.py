"""Execution result class"""

import sqlite3
import json
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import uuid

from .outputs import OutputData
from ..schema import OutputSchema
from ..config import get_config, get_logger
from ..utils.serialization import serialize_value, deserialize_value

logger = get_logger()


class ExecutionResult:
    """Container for simulation execution results"""

    def __init__(
        self,
        execution_id: str,
        simulation_id: int,
        simulation_name: str,
        simulation_version: str,
        inputs: Dict[str, Any],
        outputs: Optional[OutputData] = None,
        output_schema: Optional[OutputSchema] = None,
        output_data: Optional[Dict[str, Any]] = None,
        status: str = "completed",
        executed_at: Optional[datetime] = None,
        duration_seconds: Optional[float] = None,
        executor_type: str = "local",
        executor_config: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        cache_key: Optional[str] = None,
        squid_id: Optional[str] = None,
    ):
        """Initialize execution result

        Args:
            execution_id: Unique execution ID (UUID)
            simulation_id: Database simulation ID
            simulation_name: Simulation name
            simulation_version: Simulation version
            inputs: Input parameters used
            outputs: OutputData instance (if already created)
            output_schema: Output schema (if creating OutputData)
            output_data: Raw output data dictionary
            status: Execution status
            executed_at: Execution timestamp
            duration_seconds: Execution duration
            executor_type: Type of executor used
            executor_config: Executor configuration
            error_message: Error message if failed
            cache_key: Cache key for lookup
            squid_id: SQUID ID for this execution
        """
        self.execution_id = execution_id
        self.simulation_id = simulation_id
        self.simulation_name = simulation_name
        self.simulation_version = simulation_version
        self.inputs = inputs
        self.status = status
        self.executed_at = executed_at or datetime.now()
        self.duration_seconds = duration_seconds
        self.executor_type = executor_type
        self.executor_config = executor_config or {}
        self.error_message = error_message
        self.cache_key = cache_key
        self.squid_id = squid_id

        # Create OutputData
        if outputs is not None:
            self.outputs = outputs
        elif output_schema and output_data:
            self.outputs = OutputData(output_schema, output_data)
        else:
            self.outputs = None

        self._output_schema = output_schema
        self._output_data = output_data

    def save(self, db_path: Optional[Path] = None):
        """Save execution result to database

        Args:
            db_path: Database path (uses default if None)
        """
        if db_path is None:
            db_path = get_config().db_path

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Insert execution record
            cursor.execute("""
                INSERT INTO executions (
                    id, simulation_id, simulation_name, simulation_version,
                    executed_at, duration_seconds, executor_type, executor_config,
                    inputs, status, error_message, cache_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.execution_id,
                self.simulation_id,
                self.simulation_name,
                self.simulation_version,
                self.executed_at.isoformat(),
                self.duration_seconds,
                self.executor_type,
                serialize_value(self.executor_config),
                serialize_value(self.inputs),
                self.status,
                self.error_message,
                self.cache_key,
            ))

            # Insert outputs if available
            if self._output_data and self._output_schema:
                for name, value in self._output_data.items():
                    if name not in self._output_schema:
                        continue

                    field = self._output_schema[name]

                    # Serialize value
                    serialized = field.serialize() if hasattr(field, '_value') and field._value is not None else value

                    # Check if output already exists (may have been saved by save_outputs() in notebook)
                    cursor.execute("""
                        SELECT COUNT(*) FROM outputs
                        WHERE execution_id = ? AND name = ?
                    """, (self.execution_id, name))

                    if cursor.fetchone()[0] > 0:
                        # Output already exists, skip
                        continue

                    # Store as JSON
                    cursor.execute("""
                        INSERT INTO outputs (
                            execution_id, name, type, value
                        ) VALUES (?, ?, ?, ?)
                    """, (
                        self.execution_id,
                        name,
                        field.type_name,
                        json.dumps(serialized),
                    ))

            # Update cache if cache_key provided
            if self.cache_key:
                cursor.execute("""
                    INSERT OR REPLACE INTO cache (
                        cache_key, execution_id, created_at, last_accessed, access_count
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    self.cache_key,
                    self.execution_id,
                    self.executed_at.isoformat(),
                    self.executed_at.isoformat(),
                    1,
                ))

            conn.commit()
            logger.info(f"Saved execution {self.execution_id}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save execution: {e}")
            raise

        finally:
            conn.close()

    @classmethod
    def load(cls, execution_id: str, db_path: Optional[Path] = None) -> 'ExecutionResult':
        """Load execution result from database

        Args:
            execution_id: Execution ID to load
            db_path: Database path (uses default if None)

        Returns:
            ExecutionResult instance
        """
        if db_path is None:
            db_path = get_config().db_path

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Load execution record
            cursor.execute("""
                SELECT * FROM executions WHERE id = ?
            """, (execution_id,))

            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Execution {execution_id} not found")

            # Load outputs
            cursor.execute("""
                SELECT * FROM outputs WHERE execution_id = ?
            """, (execution_id,))

            output_data = {}
            for output_row in cursor.fetchall():
                name = output_row['name']
                value_json = output_row['value']
                output_data[name] = json.loads(value_json) if value_json else None

            # Parse timestamp
            executed_at = datetime.fromisoformat(row['executed_at'])

            # Load output schema from simulation
            output_schema = None
            try:
                from ..repository import SimulationRepository
                repo = SimulationRepository()
                sim = repo.load(row['simulation_name'], row['simulation_version'])
                if sim:
                    output_schema = sim.outputs
            except Exception as e:
                logger.debug(f"Could not load output schema for {row['simulation_name']}/{row['simulation_version']}: {e}")
                pass  # Schema not available, outputs will be None

            # Create result
            result = cls(
                execution_id=row['id'],
                simulation_id=row['simulation_id'],
                simulation_name=row['simulation_name'],
                simulation_version=row['simulation_version'],
                inputs=json.loads(row['inputs']),
                output_data=output_data,
                output_schema=output_schema,
                status=row['status'],
                executed_at=executed_at,
                duration_seconds=row['duration_seconds'],
                executor_type=row['executor_type'],
                executor_config=json.loads(row['executor_config']) if row['executor_config'] else {},
                error_message=row['error_message'],
                cache_key=row['cache_key'],
            )

            return result

        finally:
            conn.close()

    @classmethod
    def create(
        cls,
        simulation_id: int,
        simulation_name: str,
        simulation_version: str,
        inputs: Dict[str, Any],
        output_schema: OutputSchema,
        executor_type: str = "local",
        cache_key: Optional[str] = None,
        squid_id: Optional[str] = None,
    ) -> 'ExecutionResult':
        """Create a new execution result

        Args:
            simulation_id: Database simulation ID
            simulation_name: Simulation name
            simulation_version: Simulation version
            inputs: Input parameters
            output_schema: Output schema
            executor_type: Executor type
            cache_key: Cache key
            squid_id: SQUID ID

        Returns:
            New ExecutionResult instance
        """
        execution_id = str(uuid.uuid4())

        return cls(
            execution_id=execution_id,
            simulation_id=simulation_id,
            simulation_name=simulation_name,
            simulation_version=simulation_version,
            inputs=inputs,
            output_schema=output_schema,
            output_data={},
            executor_type=executor_type,
            cache_key=cache_key,
            squid_id=squid_id,
        )

    def set_outputs(self, output_data: Dict[str, Any]):
        """Set output data

        Args:
            output_data: Dictionary of output values
        """
        self._output_data = output_data
        if self._output_schema:
            self.outputs = OutputData(self._output_schema, output_data)

    def set_error(self, error_message: str):
        """Mark execution as failed

        Args:
            error_message: Error description
        """
        self.status = "failed"
        self.error_message = error_message

    def __repr__(self):
        return f"ExecutionResult(id={self.execution_id[:8]}..., status={self.status})"


def load_result(execution_id: str, db_path: Optional[Path] = None) -> ExecutionResult:
    """Load execution result from database (convenience function)

    Args:
        execution_id: Execution ID
        db_path: Database path

    Returns:
        ExecutionResult
    """
    return ExecutionResult.load(execution_id, db_path)
