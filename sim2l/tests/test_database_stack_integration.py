# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Integration tests for sim2l database systems.

Tests the complete workflow with run databases, cache service, and catalog.
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta

from sim2l.database import (
    RunDatabase,
    CacheClient,
    LocalCacheClient,
    CatalogClient,
    LocalCatalogClient,
    SessionManager,
    get_session_manager,
    reset_session_manager,
)


class TestRunDatabase:
    """Tests for per-run SQLite databases."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.execution_id = "test-exec-123"
        self.db_path = os.path.join(self.temp_dir, f"{self.execution_id}.db")

    def test_create_run_database(self):
        """Test creating a run database."""
        run_db = RunDatabase(self.execution_id, self.db_path)

        assert os.path.exists(self.db_path)
        assert run_db.execution_id == self.execution_id

    def test_initialize_run(self):
        """Test initializing run metadata."""
        run_db = RunDatabase(self.execution_id, self.db_path)

        run_db.initialize_run(
            simulation_name="test_sim",
            simulation_version="1.0.0",
            squid_id="test_sim/1.0.0/abc123",
            executor_type="local",
            user_id="testuser",
        )

        summary = run_db.get_summary()
        assert summary["simulation_name"] == "test_sim"
        assert summary["simulation_version"] == "1.0.0"
        assert summary["status"] == "running"

    def test_save_inputs(self):
        """Test saving inputs."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        run_db.save_input("temperature", 350.0, "Number", units="kelvin")
        run_db.save_input("pressure", 101325, "Integer", units="pascal")

        inputs = run_db.get_inputs()
        assert len(inputs) == 2
        assert inputs["temperature"]["value"] == 350.0
        assert inputs["temperature"]["units"] == "kelvin"

    def test_save_outputs(self):
        """Test saving outputs."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        run_db.save_output("max_temp", 425.0, "Number", units="kelvin")
        run_db.save_output("duration", 12.5, "Number", units="seconds")

        outputs = run_db.get_outputs()
        assert len(outputs) == 2
        assert outputs["max_temp"]["value"] == 425.0

    def test_logging(self):
        """Test logging functionality."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        run_db.log("INFO", "Starting simulation")
        run_db.log("WARNING", "High temperature detected")
        run_db.log("ERROR", "Simulation failed", exception_type="ValueError")

        logs = run_db.get_logs()
        assert len(logs) == 3

        errors = run_db.get_errors()
        assert len(errors) == 1
        assert errors[0]["level"] == "ERROR"

    def test_save_artifact(self):
        """Test saving artifacts."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        # Save binary artifact
        artifact_id = run_db.save_artifact(
            name="plot.png",
            content=b"fake image data",
            content_type="image/png",
            category="plot",
        )

        assert artifact_id > 0

    def test_complete_run(self):
        """Test completing a run."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        run_db.complete_run(status="completed", duration_seconds=15.5)

        summary = run_db.get_summary()
        assert summary["status"] == "completed"
        assert summary["duration_seconds"] == 15.5

    def test_complete_run_with_error(self):
        """Test completing a failed run."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        run_db.complete_run(
            status="failed",
            duration_seconds=5.0,
            error_message="ValueError: Invalid input",
            error_traceback="Traceback...",
        )

        summary = run_db.get_summary()
        assert summary["status"] == "failed"
        assert "ValueError" in summary["error_message"]

    def test_metrics(self):
        """Test saving metrics."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        run_db.save_metric("execution_time", 12.5, "seconds", category="performance")
        run_db.save_metric("iterations", 1000, category="performance")

        # Metrics saved successfully (no assertion needed, just verify no error)

    def test_tags(self):
        """Test adding tags."""
        run_db = RunDatabase(self.execution_id, self.db_path)
        run_db.initialize_run("test_sim", "1.0.0")

        run_db.add_tag("physics")
        run_db.add_tag("thermal")

        # Tags added successfully


class TestSessionManager:
    """Tests for session management."""

    def setup_method(self):
        """Setup for each test."""
        reset_session_manager()

    def test_create_user(self):
        """Test creating a user."""
        manager = SessionManager()

        user_id = manager.create_user("alice", "secret", role="developer")
        assert user_id > 0

    def test_authenticate(self):
        """Test user authentication."""
        manager = SessionManager()
        manager.create_user("alice", "secret", role="developer")

        session = manager.authenticate("alice", "secret")
        assert session.username == "alice"
        assert "write" in session.privileges
        assert "catalog_update" in session.privileges

    def test_authenticate_invalid(self):
        """Test authentication with invalid credentials."""
        manager = SessionManager()
        manager.create_user("alice", "secret")

        with pytest.raises(ValueError):
            manager.authenticate("alice", "wrong_password")

    def test_check_privilege(self):
        """Test privilege checking."""
        manager = SessionManager()
        manager.create_user("alice", "secret", role="developer")
        session = manager.authenticate("alice", "secret")

        assert manager.check_privilege(session.session_id, "read")
        assert manager.check_privilege(session.session_id, "write")
        assert manager.check_privilege(session.session_id, "catalog_update")
        assert not manager.check_privilege(session.session_id, "admin")

    def test_admin_privileges(self):
        """Test admin has all privileges."""
        manager = SessionManager()

        # Default admin user
        session = manager.authenticate("admin", "admin")
        assert manager.check_privilege(session.session_id, "admin")
        assert manager.check_privilege(session.session_id, "catalog_update")

    def test_session_expiration(self):
        """Test session expiration."""
        manager = SessionManager()
        manager.create_user("alice", "secret")

        # Create session with 0 hour TTL (immediate expiration)
        session = manager.authenticate("alice", "secret", ttl_hours=0)

        # Session should be invalid
        assert not manager.validate_session(session.session_id)

    def test_anonymous_session(self):
        """Test creating anonymous session."""
        manager = SessionManager()

        session = manager.create_anonymous_session(privileges=["read", "write"])
        assert session.username == "anonymous"
        assert "read" in session.privileges
        assert "write" in session.privileges


class TestLocalCacheClient:
    """Tests for local cache client."""

    def test_cache_hit(self):
        """Test cache hit."""
        cache = LocalCacheClient()

        # Set cache entry
        cache.set(
            cache_key="key123",
            simulation_id=1,
            simulation_name="test_sim",
            simulation_version="1.0.0",
            execution_id="exec-123",
            squid_id="test/1.0.0/abc",
            input_hash="hash456",
            run_db_path="/path/to/run.db",
        )

        # Get cache entry
        result = cache.get("key123")
        assert result is not None
        assert result["execution_id"] == "exec-123"
        assert result["squid_id"] == "test/1.0.0/abc"

    def test_cache_miss(self):
        """Test cache miss."""
        cache = LocalCacheClient()

        result = cache.get("nonexistent")
        assert result is None

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        cache = LocalCacheClient()

        # Set multiple entries
        cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/a",
            input_hash="hash1",
            run_db_path="/path1",
        )
        cache.set(
            cache_key="key2",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec2",
            squid_id="sim1/1.0.0/b",
            input_hash="hash2",
            run_db_path="/path2",
        )

        # Invalidate by simulation
        count = cache.invalidate(simulation_id=1)
        assert count == 2

        # Both should be gone
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = LocalCacheClient()

        # Set entry
        cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/a",
            input_hash="hash1",
            run_db_path="/path1",
        )

        # Get (hit)
        cache.get("key1")

        # Get (miss)
        cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats["total_requests"] == 2
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["hit_rate_percent"] == 50.0

    def test_cache_ttl(self):
        """Test cache expiration with TTL."""
        cache = LocalCacheClient()

        # Set entry with 0 second TTL (immediate expiration)
        cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/a",
            input_hash="hash1",
            run_db_path="/path1",
            ttl_seconds=0,
        )

        # Should be expired
        result = cache.get("key1")
        assert result is None


class TestLocalCatalogClient:
    """Tests for local catalog client."""

    def setup_method(self):
        """Setup for each test."""
        # Create temporary repository
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = os.path.join(self.temp_dir, "test_repo.db")

    def test_search_empty(self):
        """Test searching empty catalog."""
        catalog = LocalCatalogClient(repository_path=self.repo_path)

        results = catalog.search()
        assert len(results) == 0

    def test_health_check(self):
        """Test health check."""
        catalog = LocalCatalogClient(repository_path=self.repo_path)

        assert catalog.health_check()


class TestIntegration:
    """Integration tests combining multiple systems."""

    def setup_method(self):
        """Setup for each test."""
        self.temp_dir = tempfile.mkdtemp()
        reset_session_manager()

    def test_complete_workflow(self):
        """Test a complete workflow with all systems."""
        # 1. Create session
        manager = get_session_manager()
        manager.create_user("testuser", "password", role="developer")
        session = manager.authenticate("testuser", "password")

        # 2. Create run database
        execution_id = "integration-test-123"
        run_db = RunDatabase(
            execution_id, os.path.join(self.temp_dir, f"{execution_id}.db")
        )

        run_db.initialize_run(
            simulation_name="integration_sim",
            simulation_version="1.0.0",
            squid_id="integration/1.0.0/xyz",
            session_id=session.session_id,
        )

        # 3. Save inputs
        run_db.save_input("param1", 100, "Integer")
        run_db.save_input("param2", 3.14, "Number")

        # 4. Save outputs
        run_db.save_output("result", 314, "Integer")

        # 5. Log execution
        run_db.log("INFO", "Execution completed successfully")

        # 6. Complete run
        run_db.complete_run(status="completed", duration_seconds=1.5)

        # 7. Use local cache
        cache = LocalCacheClient(session_id=session.session_id)

        cache.set(
            cache_key="integration_cache_key",
            simulation_id=1,
            simulation_name="integration_sim",
            simulation_version="1.0.0",
            execution_id=execution_id,
            squid_id="integration/1.0.0/xyz",
            input_hash="hash_int",
            run_db_path=run_db.db_path,
        )

        # 8. Verify cache
        cached = cache.get("integration_cache_key")
        assert cached is not None
        assert cached["execution_id"] == execution_id

        # 9. Verify run database
        summary = run_db.get_summary()
        assert summary["status"] == "completed"
        assert summary["input_count"] == 2
        assert summary["output_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
