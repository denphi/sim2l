"""
Per-run SQLite database for complete run isolation.

Each execution run gets its own SQLite database containing all inputs,
outputs, files, logs, and metadata for that run.
"""

import os
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import logging


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (DB-compatible)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

logger = logging.getLogger(__name__)


class RunDatabase:
    """
    Manages a per-run SQLite database.

    Each run gets a dedicated database file that stores all data
    related to that specific execution, enabling complete isolation
    and portability.
    """

    def __init__(self, execution_id: str, db_path: Optional[str] = None):
        """
        Initialize a run database.

        Args:
            execution_id: Unique execution ID
            db_path: Path to database file (default: ~/.sim2l/runs/{execution_id}.db)
        """
        self.execution_id = execution_id

        if db_path is None:
            runs_dir = Path.home() / ".sim2l" / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(runs_dir / f"{execution_id}.db")

        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

        self._ensure_initialized()

    def _ensure_initialized(self):
        """Ensure database exists and schema is created."""
        is_new = not os.path.exists(self.db_path)

        if is_new:
            self._create_schema()
            logger.info(f"Created new run database: {self.db_path}")
        else:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            logger.debug(f"Connected to existing run database: {self.db_path}")

    def _create_schema(self):
        """Create database schema."""
        # Read schema from SQL file
        schema_path = Path(__file__).parent / "run_db_schema.sql"

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        self.conn.executescript(schema_sql)
        self.conn.commit()

    def initialize_run(
        self,
        simulation_name: str,
        simulation_version: str,
        simulation_id: Optional[int] = None,
        squid_id: Optional[str] = None,
        executor_type: str = "local",
        executor_config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        environment: Optional[Dict[str, Any]] = None,
        cache_key: Optional[str] = None,
        cache_hit: bool = False,
    ):
        """
        Initialize run metadata.

        Should be called at the start of execution.
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO run_metadata (
                execution_id, squid_id, simulation_name, simulation_version,
                simulation_id, started_at, status, executor_type, executor_config,
                cache_key, cache_hit, user_id, session_id, environment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.execution_id,
                squid_id,
                simulation_name,
                simulation_version,
                simulation_id,
                _utcnow(),
                "running",
                executor_type,
                json.dumps(executor_config) if executor_config else None,
                cache_key,
                cache_hit,
                user_id,
                session_id,
                json.dumps(environment) if environment else None,
            ),
        )

        self.conn.commit()
        logger.info(f"Initialized run {self.execution_id} for {simulation_name}/{simulation_version}")

    def complete_run(
        self,
        status: str = "completed",
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        error_traceback: Optional[str] = None,
    ):
        """
        Mark run as completed.

        Args:
            status: 'completed', 'failed', or 'cached'
            duration_seconds: Total execution time
            error_message: Error message if failed
            error_traceback: Full traceback if failed
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            UPDATE run_metadata
            SET completed_at = ?,
                status = ?,
                duration_seconds = ?,
                error_message = ?,
                error_traceback = ?
            WHERE execution_id = ?
            """,
            (
                _utcnow(),
                status,
                duration_seconds,
                error_message,
                error_traceback,
                self.execution_id,
            ),
        )

        self.conn.commit()
        logger.info(f"Run {self.execution_id} completed with status: {status}")

    def save_input(
        self,
        name: str,
        value: Any,
        field_type: str,
        units: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Save an input parameter."""
        cursor = self.conn.cursor()

        # Serialize value
        if isinstance(value, (bytes, bytearray)):
            value_str = None
            value_blob = value
        else:
            value_str = json.dumps(value)
            value_blob = None

        cursor.execute(
            """
            INSERT OR REPLACE INTO inputs (name, type, value, value_blob, units, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                field_type,
                value_str,
                value_blob,
                units,
                json.dumps(metadata) if metadata else None,
            ),
        )

        self.conn.commit()

    def save_output(
        self,
        name: str,
        value: Any,
        field_type: str,
        units: Optional[str] = None,
        file_reference: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Save an output value."""
        cursor = self.conn.cursor()

        # Serialize value
        if isinstance(value, (bytes, bytearray)):
            value_str = None
            value_blob = value
        else:
            value_str = json.dumps(value)
            value_blob = None

        cursor.execute(
            """
            INSERT OR REPLACE INTO outputs (name, type, value, value_blob, units, file_reference, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                field_type,
                value_str,
                value_blob,
                units,
                file_reference,
                json.dumps(metadata) if metadata else None,
            ),
        )

        self.conn.commit()

    def save_artifact(
        self,
        name: str,
        path: Optional[str] = None,
        content: Optional[bytes] = None,
        content_type: Optional[str] = None,
        category: str = "output",
        description: Optional[str] = None,
        external_path: Optional[str] = None,
    ) -> int:
        """
        Save an artifact (file).

        Args:
            name: Artifact name
            path: Relative path within run directory
            content: File content (stored in DB)
            content_type: MIME type
            category: 'input', 'output', 'intermediate', 'notebook', 'plot', 'data'
            description: Description
            external_path: Path to file outside database

        Returns:
            Artifact ID
        """
        import hashlib

        cursor = self.conn.cursor()

        # Compute content hash
        content_hash = None
        size_bytes = None
        if content:
            content_hash = hashlib.sha256(content).hexdigest()
            size_bytes = len(content)
        elif external_path and os.path.exists(external_path):
            # Use chunked reads to avoid loading large files entirely into memory
            hasher = hashlib.sha256()
            size_bytes = 0
            with open(external_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
                    size_bytes += len(chunk)
            content_hash = hasher.hexdigest()

        cursor.execute(
            """
            INSERT INTO artifacts (
                name, path, content_hash, content_type, size_bytes,
                category, data, external_path, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                path,
                content_hash,
                content_type,
                size_bytes,
                category,
                content,
                external_path,
                description,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def log(
        self,
        level: str,
        message: str,
        logger_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        exception_type: Optional[str] = None,
        exception_message: Optional[str] = None,
        stack_trace: Optional[str] = None,
    ):
        """
        Add a log entry.

        Args:
            level: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
            message: Log message
            logger_name: Logger name
            context: Additional context (cell number, function name, etc.)
            exception_type: Exception class name
            exception_message: Exception message
            stack_trace: Full stack trace
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO logs (
                level, logger, message, context,
                exception_type, exception_message, stack_trace
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                level,
                logger_name,
                message,
                json.dumps(context) if context else None,
                exception_type,
                exception_message,
                stack_trace,
            ),
        )

        self.conn.commit()

    def log_cell_execution(
        self,
        cell_index: int,
        cell_type: str,
        source_code: str,
        status: str = "pending",
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        duration_seconds: Optional[float] = None,
        output_text: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_traceback: Optional[str] = None,
    ) -> int:
        """Log a notebook cell execution."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO cell_executions (
                cell_index, cell_type, started_at, completed_at, duration_seconds,
                status, source_code, output_text, output_data,
                error_message, error_traceback
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cell_index,
                cell_type,
                started_at,
                completed_at,
                duration_seconds,
                status,
                source_code,
                output_text,
                json.dumps(output_data) if output_data else None,
                error_message,
                error_traceback,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def save_metric(
        self,
        metric_name: str,
        metric_value: float,
        metric_unit: Optional[str] = None,
        category: str = "custom",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Save a performance or custom metric."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO metrics (metric_name, metric_value, metric_unit, category, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                metric_name,
                metric_value,
                metric_unit,
                category,
                json.dumps(metadata) if metadata else None,
            ),
        )

        self.conn.commit()

    def save_resource_usage(
        self,
        cpu_percent: Optional[float] = None,
        memory_mb: Optional[float] = None,
        memory_percent: Optional[float] = None,
        disk_read_mb: Optional[float] = None,
        disk_write_mb: Optional[float] = None,
        network_sent_mb: Optional[float] = None,
        network_recv_mb: Optional[float] = None,
    ):
        """Save resource usage snapshot."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO resource_usage (
                cpu_percent, memory_mb, memory_percent,
                disk_read_mb, disk_write_mb, network_sent_mb, network_recv_mb
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cpu_percent,
                memory_mb,
                memory_percent,
                disk_read_mb,
                disk_write_mb,
                network_sent_mb,
                network_recv_mb,
            ),
        )

        self.conn.commit()

    def add_tag(self, tag: str):
        """Add a tag to this run."""
        cursor = self.conn.cursor()

        # Insert tag if not exists
        cursor.execute("INSERT OR IGNORE INTO tags (tag) VALUES (?)", (tag,))

        # Get tag ID
        cursor.execute("SELECT id FROM tags WHERE tag = ?", (tag,))
        tag_id = cursor.fetchone()[0]

        # Link to run
        cursor.execute("INSERT OR IGNORE INTO run_tags (tag_id) VALUES (?)", (tag_id,))

        self.conn.commit()

    def get_summary(self) -> Dict[str, Any]:
        """Get run summary."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT * FROM run_summary")
        row = cursor.fetchone()

        if row:
            return dict(row)
        else:
            return {}

    def get_inputs(self) -> Dict[str, Any]:
        """Get all inputs."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inputs")

        inputs = {}
        for row in cursor.fetchall():
            name = row["name"]
            if row["value_blob"]:
                value = row["value_blob"]
            else:
                value = json.loads(row["value"]) if row["value"] else None

            inputs[name] = {
                "value": value,
                "type": row["type"],
                "units": row["units"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            }

        return inputs

    def get_outputs(self) -> Dict[str, Any]:
        """Get all outputs."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM outputs ORDER BY created_at")

        outputs = {}
        for row in cursor.fetchall():
            name = row["name"]
            if row["value_blob"]:
                value = row["value_blob"]
            else:
                value = json.loads(row["value"]) if row["value"] else None

            outputs[name] = {
                "value": value,
                "type": row["type"],
                "units": row["units"],
                "file_reference": row["file_reference"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "created_at": row["created_at"],
            }

        return outputs

    def get_logs(
        self, level: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get logs, optionally filtered by level and limited to `limit` rows."""
        cursor = self.conn.cursor()

        params: list = []
        query = "SELECT * FROM logs"

        if level:
            query += " WHERE level = ?"
            params.append(level)

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)

        logs = []
        for row in cursor.fetchall():
            logs.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "level": row["level"],
                    "logger": row["logger"],
                    "message": row["message"],
                    "context": json.loads(row["context"]) if row["context"] else None,
                    "exception_type": row["exception_type"],
                    "exception_message": row["exception_message"],
                    "stack_trace": row["stack_trace"],
                }
            )

        return logs

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get all error logs."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM error_summary")

        errors = []
        for row in cursor.fetchall():
            errors.append(dict(row))

        return errors

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def get_size_bytes(self) -> int:
        """Get database file size in bytes."""
        if os.path.exists(self.db_path):
            return os.path.getsize(self.db_path)
        return 0
