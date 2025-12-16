"""
Comprehensive unit tests for RunDatabase.

Tests all functionality of per-run SQLite databases with high coverage.
"""

import pytest
import tempfile
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from sim2l.database.run_database import RunDatabase


class TestRunDatabaseInit:
    """Tests for RunDatabase initialization."""

    def test_create_new_database(self):
        """Test creating a new run database."""
        with tempfile.TemporaryDirectory() as temp_dir:
            execution_id = "test-exec-001"
            db_path = os.path.join(temp_dir, f"{execution_id}.db")

            run_db = RunDatabase(execution_id, db_path)

            assert os.path.exists(db_path)
            assert run_db.execution_id == execution_id
            assert run_db.db_path == db_path
            assert run_db.conn is not None

    def test_default_db_path(self):
        """Test default database path creation."""
        execution_id = "test-exec-002"

        run_db = RunDatabase(execution_id)

        expected_path = Path.home() / ".sim2l" / "runs" / f"{execution_id}.db"
        assert run_db.db_path == str(expected_path)
        assert os.path.exists(run_db.db_path)

        # Cleanup
        os.remove(run_db.db_path)

    def test_schema_creation(self):
        """Test that all tables are created."""
        with tempfile.TemporaryDirectory() as temp_dir:
            execution_id = "test-exec-003"
            db_path = os.path.join(temp_dir, f"{execution_id}.db")

            run_db = RunDatabase(execution_id, db_path)

            # Check all expected tables exist
            cursor = run_db.conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                "artifacts",
                "cell_executions",
                "checkpoints",
                "inputs",
                "logs",
                "metrics",
                "outputs",
                "provenance",
                "resource_usage",
                "run_metadata",
                "run_tags",
                "tags",
            ]

            for table in expected_tables:
                assert table in tables, f"Table {table} not created"

    def test_connect_to_existing_database(self):
        """Test connecting to an existing database."""
        with tempfile.TemporaryDirectory() as temp_dir:
            execution_id = "test-exec-004"
            db_path = os.path.join(temp_dir, f"{execution_id}.db")

            # Create database
            run_db1 = RunDatabase(execution_id, db_path)
            run_db1.initialize_run("test_sim", "1.0.0")
            run_db1.close()

            # Reconnect
            run_db2 = RunDatabase(execution_id, db_path)

            summary = run_db2.get_summary()
            assert summary["simulation_name"] == "test_sim"


class TestRunMetadata:
    """Tests for run metadata operations."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-metadata-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)

    def test_initialize_run_basic(self):
        """Test basic run initialization."""
        self.run_db.initialize_run(
            simulation_name="test_simulation",
            simulation_version="1.0.0",
        )

        summary = self.run_db.get_summary()
        assert summary["execution_id"] == self.execution_id
        assert summary["simulation_name"] == "test_simulation"
        assert summary["simulation_version"] == "1.0.0"
        assert summary["status"] == "running"

    def test_initialize_run_with_all_fields(self):
        """Test run initialization with all optional fields."""
        self.run_db.initialize_run(
            simulation_name="test_simulation",
            simulation_version="2.0.0",
            simulation_id=42,
            squid_id="test/2.0.0/abc123",
            executor_type="notebook",
            executor_config={"timeout": 300, "kernel": "python3"},
            user_id="testuser",
            session_id="session-xyz",
            environment={"python": "3.11", "os": "linux"},
            cache_key="cache-key-123",
            cache_hit=True,
        )

        summary = self.run_db.get_summary()
        assert summary["simulation_id"] == 42
        assert summary["squid_id"] == "test/2.0.0/abc123"
        assert summary["executor_type"] == "notebook"
        assert summary["user_id"] == "testuser"
        assert summary["cache_hit"] == 1  # SQLite boolean

    def test_complete_run_success(self):
        """Test completing a successful run."""
        self.run_db.initialize_run("test_sim", "1.0.0")

        self.run_db.complete_run(status="completed", duration_seconds=12.5)

        summary = self.run_db.get_summary()
        assert summary["status"] == "completed"
        assert summary["duration_seconds"] == 12.5
        assert summary["completed_at"] is not None

    def test_complete_run_failure(self):
        """Test completing a failed run."""
        self.run_db.initialize_run("test_sim", "1.0.0")

        self.run_db.complete_run(
            status="failed",
            duration_seconds=5.0,
            error_message="ValueError: Invalid input parameter",
            error_traceback="Traceback (most recent call last):\n  File ...",
        )

        summary = self.run_db.get_summary()
        assert summary["status"] == "failed"
        assert "ValueError" in summary["error_message"]
        assert summary["error_traceback"] is not None

    def test_complete_run_cached(self):
        """Test completing a cached run."""
        self.run_db.initialize_run("test_sim", "1.0.0", cache_hit=True)

        self.run_db.complete_run(status="cached", duration_seconds=0.1)

        summary = self.run_db.get_summary()
        assert summary["status"] == "cached"
        assert summary["cache_hit"] == 1


class TestInputsOutputs:
    """Tests for inputs and outputs storage."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-io-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)
        self.run_db.initialize_run("test_sim", "1.0.0")

    def test_save_input_integer(self):
        """Test saving integer input."""
        self.run_db.save_input("count", 100, "Integer")

        inputs = self.run_db.get_inputs()
        assert "count" in inputs
        assert inputs["count"]["value"] == 100
        assert inputs["count"]["type"] == "Integer"

    def test_save_input_float(self):
        """Test saving float input."""
        self.run_db.save_input("temperature", 350.5, "Number", units="kelvin")

        inputs = self.run_db.get_inputs()
        assert inputs["temperature"]["value"] == 350.5
        assert inputs["temperature"]["units"] == "kelvin"

    def test_save_input_string(self):
        """Test saving string input."""
        self.run_db.save_input("mode", "fast", "Text")

        inputs = self.run_db.get_inputs()
        assert inputs["mode"]["value"] == "fast"

    def test_save_input_list(self):
        """Test saving list input."""
        self.run_db.save_input("values", [1, 2, 3, 4, 5], "Array")

        inputs = self.run_db.get_inputs()
        assert inputs["values"]["value"] == [1, 2, 3, 4, 5]

    def test_save_input_dict(self):
        """Test saving dictionary input."""
        config = {"param1": 10, "param2": 20}
        self.run_db.save_input("config", config, "Dict")

        inputs = self.run_db.get_inputs()
        assert inputs["config"]["value"] == config

    def test_save_input_with_metadata(self):
        """Test saving input with metadata."""
        metadata = {"source": "user", "validated": True}
        self.run_db.save_input("param", 42, "Integer", metadata=metadata)

        inputs = self.run_db.get_inputs()
        assert inputs["param"]["metadata"] == metadata

    def test_save_input_binary(self):
        """Test saving binary input."""
        binary_data = b"\x00\x01\x02\x03\x04"
        self.run_db.save_input("binary_param", binary_data, "Binary")

        inputs = self.run_db.get_inputs()
        assert inputs["binary_param"]["value"] == binary_data

    def test_save_multiple_inputs(self):
        """Test saving multiple inputs."""
        self.run_db.save_input("param1", 100, "Integer")
        self.run_db.save_input("param2", 3.14, "Number")
        self.run_db.save_input("param3", "test", "Text")

        inputs = self.run_db.get_inputs()
        assert len(inputs) == 3

    def test_replace_input(self):
        """Test replacing an existing input."""
        self.run_db.save_input("param", 100, "Integer")
        self.run_db.save_input("param", 200, "Integer")

        inputs = self.run_db.get_inputs()
        assert inputs["param"]["value"] == 200

    def test_save_output(self):
        """Test saving output."""
        self.run_db.save_output("result", 42, "Integer")

        outputs = self.run_db.get_outputs()
        assert "result" in outputs
        assert outputs["result"]["value"] == 42

    def test_save_output_with_units(self):
        """Test saving output with units."""
        self.run_db.save_output("max_temp", 425.0, "Number", units="kelvin")

        outputs = self.run_db.get_outputs()
        assert outputs["max_temp"]["units"] == "kelvin"

    def test_save_output_with_file_reference(self):
        """Test saving output with file reference."""
        self.run_db.save_output(
            "plot", None, "Image", file_reference="artifacts/plot.png"
        )

        outputs = self.run_db.get_outputs()
        assert outputs["plot"]["file_reference"] == "artifacts/plot.png"

    def test_save_output_with_metadata(self):
        """Test saving output with metadata."""
        metadata = {"computation_time": 1.5, "algorithm": "gradient_descent"}
        self.run_db.save_output("optimized_value", 3.14, "Number", metadata=metadata)

        outputs = self.run_db.get_outputs()
        assert outputs["optimized_value"]["metadata"] == metadata

    def test_get_outputs_empty(self):
        """Test getting outputs when none exist."""
        outputs = self.run_db.get_outputs()
        assert len(outputs) == 0

    def test_get_inputs_empty(self):
        """Test getting inputs when none exist."""
        inputs = self.run_db.get_inputs()
        assert len(inputs) == 0


class TestLogging:
    """Tests for logging functionality."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-log-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)
        self.run_db.initialize_run("test_sim", "1.0.0")

    def test_log_info(self):
        """Test logging INFO level message."""
        self.run_db.log("INFO", "Starting simulation")

        logs = self.run_db.get_logs()
        assert len(logs) == 1
        assert logs[0]["level"] == "INFO"
        assert logs[0]["message"] == "Starting simulation"

    def test_log_warning(self):
        """Test logging WARNING level message."""
        self.run_db.log("WARNING", "High temperature detected")

        logs = self.run_db.get_logs()
        assert logs[0]["level"] == "WARNING"

    def test_log_error(self):
        """Test logging ERROR level message."""
        self.run_db.log("ERROR", "Computation failed")

        logs = self.run_db.get_logs()
        assert logs[0]["level"] == "ERROR"

    def test_log_with_logger_name(self):
        """Test logging with logger name."""
        self.run_db.log("INFO", "Message", logger_name="sim2l.executor")

        logs = self.run_db.get_logs()
        assert logs[0]["logger"] == "sim2l.executor"

    def test_log_with_context(self):
        """Test logging with context."""
        context = {"cell_number": 5, "function": "compute"}
        self.run_db.log("DEBUG", "Computing...", context=context)

        logs = self.run_db.get_logs()
        assert logs[0]["context"] == context

    def test_log_with_exception(self):
        """Test logging with exception details."""
        self.run_db.log(
            "ERROR",
            "Division by zero",
            exception_type="ZeroDivisionError",
            exception_message="division by zero",
            stack_trace="Traceback...",
        )

        logs = self.run_db.get_logs()
        assert logs[0]["exception_type"] == "ZeroDivisionError"
        assert logs[0]["stack_trace"] is not None

    def test_get_logs_by_level(self):
        """Test filtering logs by level."""
        self.run_db.log("INFO", "Info message")
        self.run_db.log("WARNING", "Warning message")
        self.run_db.log("ERROR", "Error message")

        error_logs = self.run_db.get_logs(level="ERROR")
        assert len(error_logs) == 1
        assert error_logs[0]["level"] == "ERROR"

    def test_get_logs_with_limit(self):
        """Test limiting number of logs returned."""
        for i in range(10):
            self.run_db.log("INFO", f"Message {i}")

        logs = self.run_db.get_logs(limit=5)
        assert len(logs) == 5

    def test_get_errors(self):
        """Test getting error summary."""
        self.run_db.log("INFO", "Normal operation")
        self.run_db.log("ERROR", "Error 1", exception_type="ValueError")
        self.run_db.log("CRITICAL", "Error 2", exception_type="RuntimeError")

        errors = self.run_db.get_errors()
        assert len(errors) == 2

    def test_multiple_logs(self):
        """Test logging multiple messages."""
        for i in range(5):
            self.run_db.log("INFO", f"Step {i}")

        logs = self.run_db.get_logs()
        assert len(logs) == 5


class TestArtifacts:
    """Tests for artifact storage."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-artifact-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)
        self.run_db.initialize_run("test_sim", "1.0.0")

    def test_save_artifact_with_content(self):
        """Test saving artifact with binary content."""
        content = b"fake image data"
        artifact_id = self.run_db.save_artifact(
            name="plot.png",
            content=content,
            content_type="image/png",
            category="plot",
        )

        assert artifact_id > 0

    def test_save_artifact_with_path(self):
        """Test saving artifact with path."""
        artifact_id = self.run_db.save_artifact(
            name="results.csv", path="outputs/results.csv", category="data"
        )

        assert artifact_id > 0

    def test_save_artifact_with_external_path(self):
        """Test saving artifact with external file path."""
        # Create a temporary file
        temp_file = os.path.join(self.temp_dir, "test_file.txt")
        with open(temp_file, "w") as f:
            f.write("test content")

        artifact_id = self.run_db.save_artifact(
            name="test.txt",
            external_path=temp_file,
            content_type="text/plain",
            category="input",
        )

        assert artifact_id > 0

    def test_save_artifact_with_description(self):
        """Test saving artifact with description."""
        artifact_id = self.run_db.save_artifact(
            name="analysis.pdf",
            content=b"pdf data",
            description="Final analysis report",
            category="output",
        )

        assert artifact_id > 0

    def test_save_multiple_artifacts(self):
        """Test saving multiple artifacts."""
        for i in range(3):
            self.run_db.save_artifact(
                name=f"artifact_{i}.dat", content=b"data", category="intermediate"
            )

        # Verify they're saved (would need query to check)

    def test_artifact_categories(self):
        """Test different artifact categories."""
        categories = ["input", "output", "intermediate", "notebook", "plot", "data"]

        for category in categories:
            self.run_db.save_artifact(
                name=f"{category}.txt", content=b"test", category=category
            )


class TestMetrics:
    """Tests for metrics storage."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-metric-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)
        self.run_db.initialize_run("test_sim", "1.0.0")

    def test_save_performance_metric(self):
        """Test saving performance metric."""
        self.run_db.save_metric(
            "execution_time", 12.5, "seconds", category="performance"
        )

        # Metric saved successfully

    def test_save_metric_with_metadata(self):
        """Test saving metric with metadata."""
        metadata = {"algorithm": "gradient_descent", "iterations": 100}
        self.run_db.save_metric(
            "convergence_rate", 0.95, category="performance", metadata=metadata
        )

    def test_save_multiple_metrics(self):
        """Test saving multiple metrics."""
        metrics = [
            ("cpu_time", 10.0, "seconds"),
            ("memory_peak", 512, "MB"),
            ("iterations", 1000, None),
        ]

        for name, value, unit in metrics:
            self.run_db.save_metric(name, value, unit, category="performance")

    def test_save_custom_metric(self):
        """Test saving custom metric."""
        self.run_db.save_metric("custom_score", 0.87, category="custom")


class TestResourceUsage:
    """Tests for resource usage tracking."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-resource-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)
        self.run_db.initialize_run("test_sim", "1.0.0")

    def test_save_resource_usage_full(self):
        """Test saving full resource usage snapshot."""
        self.run_db.save_resource_usage(
            cpu_percent=75.5,
            memory_mb=512.0,
            memory_percent=25.0,
            disk_read_mb=10.5,
            disk_write_mb=5.2,
            network_sent_mb=1.0,
            network_recv_mb=2.0,
        )

    def test_save_resource_usage_partial(self):
        """Test saving partial resource usage."""
        self.run_db.save_resource_usage(cpu_percent=50.0, memory_mb=256.0)

    def test_save_multiple_resource_snapshots(self):
        """Test saving multiple resource usage snapshots."""
        for i in range(5):
            self.run_db.save_resource_usage(
                cpu_percent=50.0 + i * 5, memory_mb=256.0 + i * 10
            )


class TestCellExecutions:
    """Tests for notebook cell execution tracking."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-cell-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)
        self.run_db.initialize_run("test_sim", "1.0.0")

    def test_log_cell_execution(self):
        """Test logging cell execution."""
        cell_id = self.run_db.log_cell_execution(
            cell_index=0,
            cell_type="code",
            source_code="print('hello')",
            status="completed",
            duration_seconds=0.1,
        )

        assert cell_id > 0

    def test_log_cell_execution_with_output(self):
        """Test logging cell with output."""
        output_data = {"text/plain": "hello"}

        self.run_db.log_cell_execution(
            cell_index=1,
            cell_type="code",
            source_code="x = 1 + 1",
            status="completed",
            output_text="",
            output_data=output_data,
        )

    def test_log_cell_execution_failed(self):
        """Test logging failed cell execution."""
        self.run_db.log_cell_execution(
            cell_index=2,
            cell_type="code",
            source_code="1/0",
            status="failed",
            error_message="ZeroDivisionError",
            error_traceback="Traceback...",
        )

    def test_log_markdown_cell(self):
        """Test logging markdown cell."""
        self.run_db.log_cell_execution(
            cell_index=0,
            cell_type="markdown",
            source_code="# Title",
            status="skipped",
        )


class TestTags:
    """Tests for tagging functionality."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-tag-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)
        self.run_db.initialize_run("test_sim", "1.0.0")

    def test_add_single_tag(self):
        """Test adding a single tag."""
        self.run_db.add_tag("physics")

    def test_add_multiple_tags(self):
        """Test adding multiple tags."""
        tags = ["physics", "thermal", "simulation"]
        for tag in tags:
            self.run_db.add_tag(tag)

    def test_add_duplicate_tag(self):
        """Test adding duplicate tag (should not error)."""
        self.run_db.add_tag("physics")
        self.run_db.add_tag("physics")  # Should not raise error


class TestSummary:
    """Tests for summary views."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-summary-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)

    def test_get_summary_complete_run(self):
        """Test getting summary of complete run."""
        self.run_db.initialize_run("test_sim", "1.0.0")
        self.run_db.save_input("param1", 100, "Integer")
        self.run_db.save_output("result", 200, "Integer")
        self.run_db.log("INFO", "Test log")
        self.run_db.log("ERROR", "Test error")
        self.run_db.log("WARNING", "Test warning")
        self.run_db.complete_run(status="completed", duration_seconds=5.0)

        summary = self.run_db.get_summary()

        assert summary["status"] == "completed"
        assert summary["duration_seconds"] == 5.0
        assert summary["input_count"] == 1
        assert summary["output_count"] == 1
        assert summary["log_count"] == 3
        assert summary["error_count"] == 1
        assert summary["warning_count"] == 1


class TestContextManager:
    """Tests for context manager functionality."""

    def test_context_manager_success(self):
        """Test using run database as context manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            execution_id = "test-ctx-001"
            db_path = os.path.join(temp_dir, f"{execution_id}.db")

            with RunDatabase(execution_id, db_path) as run_db:
                run_db.initialize_run("test_sim", "1.0.0")
                assert run_db.conn is not None

            # Connection should be closed after exiting context

    def test_context_manager_with_exception(self):
        """Test context manager with exception."""
        with tempfile.TemporaryDirectory() as temp_dir:
            execution_id = "test-ctx-002"
            db_path = os.path.join(temp_dir, f"{execution_id}.db")

            try:
                with RunDatabase(execution_id, db_path) as run_db:
                    run_db.initialize_run("test_sim", "1.0.0")
                    raise ValueError("Test exception")
            except ValueError:
                pass

            # Connection should still be closed


class TestUtilities:
    """Tests for utility methods."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-util-001"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")
        self.run_db = RunDatabase(self.execution_id, self.db_path)

    def test_get_size_bytes(self):
        """Test getting database file size."""
        self.run_db.initialize_run("test_sim", "1.0.0")

        size = self.run_db.get_size_bytes()
        assert size > 0

    def test_close(self):
        """Test closing database connection."""
        self.run_db.initialize_run("test_sim", "1.0.0")
        self.run_db.close()

        assert self.run_db.conn is None

    def test_close_idempotent(self):
        """Test that close can be called multiple times."""
        self.run_db.close()
        self.run_db.close()  # Should not error


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=sim2l.database.run_database"])
