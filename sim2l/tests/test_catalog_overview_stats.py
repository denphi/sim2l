"""Dashboard ``/dashboard/overview`` reads from execution_registry.

Before this fix the SQLite backend returned hardcoded zeros for
``total_executions``, ``successful_executions``, and ``cached_executions``,
so the dashboard counter stayed at 0 even when arc was successfully
recording rows via POST /executions.
"""

import sqlite3
from datetime import datetime

import pytest

from sim2l.services.catalog_service import SQLiteCatalogBackend


@pytest.fixture
def backend(tmp_path):
    db_path = str(tmp_path / "catalog.db")
    be = SQLiteCatalogBackend(db_path, no_auth=True)
    # Seed a simulation row so execution_registry's FK is satisfied.
    conn = be._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO simulations (
            id, name, version, input_schema, output_schema,
            workflow_type, workflow_hash, status
        ) VALUES (1, 'demo', '0.1.0', '{}', '{}', 'function', 'h', 'active')
        """
    )
    conn.commit()
    return be


def _insert_execution(backend, *, execution_id, status="completed", cache_hit=False, simulation_id=1):
    conn = backend._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO execution_registry (
            execution_id, squid_id, simulation_id, started_at,
            status, executor_type, cache_hit,
            output_count, artifact_count, error_count, warning_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
        """,
        (execution_id, "sq-" + execution_id, simulation_id,
         datetime.utcnow().isoformat(), status, "isolated-function",
         1 if cache_hit else 0),
    )
    conn.commit()


def test_overview_stats_empty_db(backend):
    """No rows ⇒ all counters 0."""
    result, status = backend.get_overview_stats()
    assert status == 200
    assert result["total_executions"] == 0
    assert result["successful_executions"] == 0
    assert result["cached_executions"] == 0


def test_overview_stats_counts_execution_registry_rows(backend):
    """Counter reflects rows recorded via /executions."""
    _insert_execution(backend, execution_id="e1", status="completed")
    _insert_execution(backend, execution_id="e2", status="completed")
    _insert_execution(backend, execution_id="e3", status="failed")

    result, status = backend.get_overview_stats()
    assert status == 200
    assert result["total_executions"] == 3
    assert result["successful_executions"] == 2
    assert result["cached_executions"] == 0


def test_overview_stats_counts_cache_hits(backend):
    """cache_hit=1 rows count toward cached_executions."""
    _insert_execution(backend, execution_id="e1", status="completed", cache_hit=False)
    _insert_execution(backend, execution_id="e2", status="completed", cache_hit=True)
    _insert_execution(backend, execution_id="e3", status="completed", cache_hit=True)

    result, _ = backend.get_overview_stats()
    assert result["total_executions"] == 3
    assert result["successful_executions"] == 3
    assert result["cached_executions"] == 2
