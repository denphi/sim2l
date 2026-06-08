import base64
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
import sim2l

from sim2l.services import catalog_service
from sim2l.services.results_service import SQLiteResultsBackend


class _DummyRunResult:
    execution_id = "exec-1"
    simulation_name = "tool"
    simulation_version = "0.1.0"
    squid_id = "squid-1"
    status = "completed"
    duration_seconds = 0.25
    executor_type = "isolated-function"


def test_results_register_direct_allows_multiple_blank_squid_ids(tmp_path):
    backend = SQLiteResultsBackend(str(tmp_path / "results.db"))
    for idx in range(2):
        backend.register_schema(
            "tool",
            "0.1.0",
            {"inputs": {"x": {"type": "number"}}, "outputs": {"y": {"type": "number"}}},
        )
        backend.register_result(
            execution_id=f"exec-{idx}",
            simulation_name="tool",
            simulation_version="0.1.0",
            squid_id="",
            input_params={"x": idx},
            output_params={"y": idx + 1},
            status="completed",
            duration_seconds=0.1,
            run_db_path="",
        )

    assert backend.get_result("exec-0")["output_params"]["y"] == 1
    assert backend.get_result("exec-1")["output_params"]["y"] == 2


def test_results_register_direct_updates_repeated_blank_squid_execution(tmp_path):
    backend = SQLiteResultsBackend(str(tmp_path / "results.db"))
    backend.register_schema(
        "tool",
        "0.1.0",
        {"inputs": {"x": {"type": "number"}}, "outputs": {"y": {"type": "number"}}},
    )
    for value in (1, 2):
        backend.register_result(
            execution_id="exec-repeat",
            simulation_name="tool",
            simulation_version="0.1.0",
            squid_id="",
            input_params={"x": value},
            output_params={"y": value},
            status="completed",
            duration_seconds=0.1,
            run_db_path="",
        )

    assert backend.get_result("exec-repeat")["output_params"]["y"] == 2


def test_catalog_run_executes_registered_function_bundle(tmp_path):
    old_db_path = sim2l.get_config().db_path
    sim2l.get_config().results_service_url = None
    sim2l.configure(db_path=tmp_path / "simulations.db")
    # The backend's `no_auth` flag must match the route's `require_auth`
    # (review item #4): a server in production mode no longer honors the
    # "no-auth-session" sentinel even if a client smuggles it through.
    catalog_service.catalog_db = catalog_service.SQLiteCatalogBackend(
        str(tmp_path / "catalog.db"), no_auth=True
    )
    catalog_service.require_auth = False
    app = catalog_service.app
    client = app.test_client()
    source = b"def simulate(x=1.0):\n    return {'y': x + 2}\n"
    payload = {
        "name": "catalog_function",
        "version": "0.1.0",
        "workflow_type": "function",
        "input_schema": {"x": {"type": "Number", "default": 1.0}},
        "output_schema": {"y": {"type": "Number"}},
        "workflow_bundle": {
            "workflow_type": "function",
            "entrypoint": "workflow.py",
            "files": [
                {
                    "path": "workflow.py",
                    "content_base64": base64.b64encode(source).decode("ascii"),
                }
            ],
        },
    }

    register_response = client.post("/simulations", json=payload)
    assert register_response.status_code == 201

    try:
        run_response = client.post(
            "/run",
            json={
                "simulation_name": "catalog_function",
                "version": "0.1.0",
                "params": {"x": 3},
            },
        )
    finally:
        sim2l.configure(db_path=old_db_path)

    assert run_response.status_code == 200
    assert run_response.json["status"] == "completed"
    assert run_response.json["outputs"]["y"] == pytest.approx(5.0)

    stats_response = client.get(f"/simulations/{register_response.json['id']}/stats")
    assert stats_response.status_code == 200
    assert stats_response.json["total_executions"] == 1


def test_catalog_run_uses_downstream_tokens_for_results_and_cache(tmp_path, monkeypatch):
    old_db_path = sim2l.get_config().db_path
    sim2l.configure(db_path=tmp_path / "simulations.db")
    catalog_service.catalog_db = catalog_service.SQLiteCatalogBackend(
        str(tmp_path / "catalog.db"), no_auth=True
    )
    catalog_service.require_auth = False
    client = catalog_service.app.test_client()
    source = b"def simulate(x=1.0):\n    return {'y': x + 2}\n"
    payload = {
        "name": "catalog_token_forwarding",
        "version": "0.1.0",
        "workflow_type": "function",
        "input_schema": {"x": {"type": "Number", "default": 1.0}},
        "output_schema": {"y": {"type": "Number"}},
        "workflow_bundle": {
            "workflow_type": "function",
            "entrypoint": "workflow.py",
            "files": [
                {
                    "path": "workflow.py",
                    "content_base64": base64.b64encode(source).decode("ascii"),
                }
            ],
        },
    }
    captured = {}

    def fake_register(result, params, outputs, session_id, results_session_id=None):
        captured["results"] = (session_id, results_session_id)
        return True

    def fake_cache(result, sim_record, params, session_id, cache_session_id=None):
        captured["cache"] = (session_id, cache_session_id)
        return True

    monkeypatch.setattr(catalog_service, "_register_service_result", fake_register)
    monkeypatch.setattr(catalog_service, "_store_service_cache_entry", fake_cache)

    try:
        assert client.post("/simulations", json=payload).status_code == 201
        response = client.post(
            "/run",
            headers={
                "X-Session-ID": "catalog-token",
                "X-Sim2L-Results-Session-ID": "results-token",
                "X-Sim2L-Cache-Session-ID": "cache-token",
            },
            json={
                "simulation_name": "catalog_token_forwarding",
                "version": "0.1.0",
                "params": {"x": 3},
            },
        )
    finally:
        sim2l.configure(db_path=old_db_path)

    assert response.status_code == 200
    assert response.json["persistence"] == {
        "catalog_execution": True,
        "results": True,
        "cache": True,
    }
    assert captured["results"] == ("no-auth-session", "results-token")
    assert captured["cache"] == ("no-auth-session", "cache-token")


def test_catalog_run_without_workflow_bundle_returns_conflict(tmp_path):
    catalog_service.catalog_db = catalog_service.SQLiteCatalogBackend(
        str(tmp_path / "catalog.db"), no_auth=True
    )
    catalog_service.require_auth = False
    client = catalog_service.app.test_client()
    conn = catalog_service.catalog_db._get_conn()
    conn.execute(
        """
        INSERT INTO simulations (
            name, version, workflow_type, input_schema, output_schema,
            workflow_hash, workflow_bundle, status, visibility, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "metadata_only",
            "0.1.0",
            "function",
            json.dumps({"x": {"type": "Number", "default": 1.0}}),
            json.dumps({"y": {"type": "Number"}}),
            "legacy-hash",
            None,
            "active",
            "public",
            json.dumps({"workflow_source": "def simulate(x=1): return {'y': x}"}),
        ),
    )
    conn.commit()

    run_response = client.post(
        "/run",
        json={
            "simulation_name": "metadata_only",
            "version": "0.1.0",
            "params": {"x": 3},
        },
    )

    assert run_response.status_code == 409
    assert "workflow_bundle" in run_response.json["error"]


def test_catalog_run_mirrors_results_with_downstream_token(monkeypatch):
    captured = {}
    config = sim2l.get_config()
    old_url = config.results_service_url
    old_session = config.results_session_id
    config.results_service_url = "http://results"
    config.results_session_id = None

    class FakeResultsClient:
        def __init__(self, base_url, session_id=None):
            captured["base_url"] = base_url
            captured["session_id"] = session_id

        def register_direct(self, **kwargs):
            captured["payload"] = kwargs
            return {"ok": True}

    monkeypatch.setattr(catalog_service, "ResultsClient", FakeResultsClient)
    try:
        persisted = catalog_service._register_service_result(
            _DummyRunResult(),
            {"x": 1},
            {"y": 2},
            "catalog-token",
            results_session_id="results-token",
        )
    finally:
        config.results_service_url = old_url
        config.results_session_id = old_session

    assert persisted is True
    assert captured["base_url"] == "http://results"
    assert captured["session_id"] == "results-token"
    assert captured["payload"]["execution_id"] == "exec-1"


def test_catalog_run_mirrors_cache_with_downstream_token(monkeypatch):
    captured = {}
    config = sim2l.get_config()
    old_url = config.cache_service_url
    old_session = config.cache_session_id
    config.cache_service_url = "http://cache"
    config.cache_session_id = None

    class FakeCacheClient:
        def __init__(self, service_url, session_id=None):
            captured["service_url"] = service_url
            captured["session_id"] = session_id

        def set(self, **kwargs):
            captured["payload"] = kwargs
            return True

    monkeypatch.setattr(catalog_service, "CacheClient", FakeCacheClient)
    try:
        persisted = catalog_service._store_service_cache_entry(
            _DummyRunResult(),
            {"id": 7},
            {"x": 1},
            "catalog-token",
            cache_session_id="cache-token",
        )
    finally:
        config.cache_service_url = old_url
        config.cache_session_id = old_session

    assert persisted is True
    assert captured["service_url"] == "http://cache"
    assert captured["session_id"] == "cache-token"
    assert captured["payload"]["simulation_id"] == 7
    assert captured["payload"]["cache_key"] == "squid-1"


def test_catalog_run_rejects_invalid_session(tmp_path):
    catalog_service.catalog_db = catalog_service.SQLiteCatalogBackend(str(tmp_path / "catalog.db"))
    catalog_service.require_auth = True
    try:
        response = catalog_service.app.test_client().post(
            "/run",
            headers={"X-Session-ID": "not-a-real-session"},
            json={"simulation_name": "anything", "params": {}},
        )
    finally:
        catalog_service.require_auth = False

    assert response.status_code == 401


def test_catalog_run_rejects_read_only_session(tmp_path):
    catalog_service.catalog_db = catalog_service.SQLiteCatalogBackend(str(tmp_path / "catalog.db"))
    conn = catalog_service.catalog_db._get_conn()
    conn.execute(
        "INSERT INTO users (id, username, role) VALUES (?, ?, ?)",
        (1, "reader", "user"),
    )
    # SQLite's ``datetime('now')`` returns naive UTC. Use naive UTC here too
    # so the lexicographic comparison in ``_check_session`` doesn't treat
    # a future local-time stamp as already expired.
    expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    ).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO sessions (session_id, user_id, expires_at, is_valid, privileges)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "read-session",
            1,
            expires_at,
            1,
            json.dumps(["read"]),
        ),
    )
    conn.commit()

    catalog_service.require_auth = True
    try:
        response = catalog_service.app.test_client().post(
            "/run",
            headers={"X-Session-ID": "read-session"},
            json={"simulation_name": "anything", "params": {}},
        )
    finally:
        catalog_service.require_auth = False

    assert response.status_code == 403


def test_catalog_record_execution_requires_auth(tmp_path):
    catalog_service.catalog_db = catalog_service.SQLiteCatalogBackend(str(tmp_path / "catalog.db"))
    catalog_service.require_auth = True
    try:
        response = catalog_service.app.test_client().post(
            "/executions",
            json={"execution_id": "exec-1"},
        )
    finally:
        catalog_service.require_auth = False

    assert response.status_code == 401


def test_results_backend_migrates_old_squid_schema(tmp_path):
    db_path = tmp_path / "old-results.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE execution_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL UNIQUE,
            simulation_name TEXT NOT NULL,
            simulation_version TEXT NOT NULL,
            schema_id INTEGER,
            squid_id TEXT,
            input_params TEXT NOT NULL,
            output_params TEXT,
            status TEXT DEFAULT 'pending',
            duration_seconds REAL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            run_db_path TEXT,
            metadata TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    backend = SQLiteResultsBackend(str(db_path))
    backend.register_schema(
        "tool",
        "0.1.0",
        {"inputs": {"x": {"type": "number"}}, "outputs": {"y": {"type": "number"}}},
    )
    backend.register_result(
        execution_id="exec-1",
        simulation_name="tool",
        simulation_version="0.1.0",
        squid_id="stable-squid",
        input_params={"x": 1},
        output_params={"y": 1},
        status="completed",
        duration_seconds=0.1,
        run_db_path="",
    )
    backend.register_result(
        execution_id="exec-2",
        simulation_name="tool",
        simulation_version="0.1.0",
        squid_id="stable-squid",
        input_params={"x": 2},
        output_params={"y": 2},
        status="completed",
        duration_seconds=0.1,
        run_db_path="",
    )

    assert backend.get_result("exec-1")["output_params"]["y"] == 2
