"""``record_execution`` idempotency + session user attribution.

Harness-review fixes: a re-publish of the same execution_id must update the
existing row instead of failing the UNIQUE constraint with a 500, and an
execution recorded through an authenticated session is attributed to that
session's user when the payload doesn't name one.
"""

from datetime import datetime

import pytest

from sim2l.services.catalog_service import SQLiteCatalogBackend


@pytest.fixture
def backend(tmp_path):
    db_path = str(tmp_path / "catalog.db")
    be = SQLiteCatalogBackend(db_path, no_auth=True)
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


def _payload(execution_id="e-1", **overrides):
    base = {
        "execution_id": execution_id,
        "squid_id": "sq-" + execution_id,
        "simulation_id": 1,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
        "duration_seconds": 1.0,
        "status": "completed",
        "executor_type": "isolated-function",
        "cache_hit": False,
        "output_count": 1,
        "environment": {"source": "test"},
    }
    base.update(overrides)
    return base


def _rows(backend, execution_id):
    cursor = backend._get_conn().cursor()
    cursor.execute(
        "SELECT * FROM execution_registry WHERE execution_id = ?",
        (execution_id,),
    )
    return cursor.fetchall()


def test_record_execution_inserts(backend):
    result, status = backend.record_execution(_payload())
    assert status == 201
    assert len(_rows(backend, "e-1")) == 1


def test_record_execution_is_idempotent_on_execution_id(backend):
    """A second record for the same execution_id updates, never 500s."""
    backend.record_execution(_payload(status="running"))
    result, status = backend.record_execution(
        _payload(status="completed", duration_seconds=2.5),
    )
    assert status == 201
    rows = _rows(backend, "e-1")
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert rows[0]["duration_seconds"] == 2.5


def test_cache_hits_recorded_under_distinct_ids_count_as_cached(backend):
    """The arc adapter records a cache hit under a fresh execution_id with
    cache_hit=True; the dashboard's cached counter must see it."""
    backend.record_execution(_payload("e-orig"))
    backend.record_execution(_payload("e-cachehit", cache_hit=True))

    stats, status = backend.get_overview_stats()
    assert status == 200
    assert stats["total_executions"] == 2
    assert stats["cached_executions"] == 1


def test_record_execution_attributes_user_from_session(backend):
    conn = backend._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (id, username, role) VALUES (7, 'alice', 'user')"
    )
    cursor.execute(
        """
        INSERT INTO sessions (session_id, user_id, expires_at, is_valid)
        VALUES ('sess-7', 7, '2099-01-01T00:00:00', 1)
        """
    )
    conn.commit()

    backend.record_execution(_payload(), session_id="sess-7")
    rows = _rows(backend, "e-1")
    assert rows[0]["user_id"] == 7


def test_record_execution_explicit_user_id_wins(backend):
    backend.record_execution(_payload(user_id=None), session_id=None)
    rows = _rows(backend, "e-1")
    assert rows[0]["user_id"] is None
