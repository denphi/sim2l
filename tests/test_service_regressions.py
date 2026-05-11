import base64
import json
import sqlite3
from datetime import datetime, timedelta

import pytest
import sim2l

from sim2l.services import catalog_service
from sim2l.services.results_service import SQLiteResultsBackend


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
    sim2l.get_config().results_service_url = None
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

    run_response = client.post(
        "/run",
        json={
            "simulation_name": "catalog_function",
            "version": "0.1.0",
            "params": {"x": 3},
        },
    )

    assert run_response.status_code == 200
    assert run_response.json["status"] == "completed"
    assert run_response.json["outputs"]["y"] == pytest.approx(5.0)

    stats_response = client.get(f"/simulations/{register_response.json['id']}/stats")
    assert stats_response.status_code == 200
    assert stats_response.json["total_executions"] == 1


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
    conn.execute(
        """
        INSERT INTO sessions (session_id, user_id, expires_at, is_valid, privileges)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "read-session",
            1,
            (datetime.now() + timedelta(hours=1)).isoformat(),
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
