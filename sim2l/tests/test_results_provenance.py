"""Results-service ``/provenance`` — published agent-action audit trails.

Harness-review fix: research clients (arc) publish their local provenance
JSONL to the results service so the audit trail of *how* a result was
produced outlives the client machine.
"""

import pytest

from sim2l.services.results_service import (
    SQLiteResultsBackend,
    create_results_service,
)


@pytest.fixture
def backend(tmp_path):
    return SQLiteResultsBackend(str(tmp_path / "results.db"))


def _entries():
    return [
        {
            "timestamp": "2026-06-10T00:00:00+00:00",
            "session_id": "arc-sess",
            "action": "start",
            "agent": "orchestrator",
            "artifact_id": None,
            "run_id": None,
            "inputs": {"goal": "maximize band gap"},
            "outputs": {},
            "metadata": {},
        },
        {
            "timestamp": "2026-06-10T00:01:00+00:00",
            "session_id": "arc-sess",
            "action": "run",
            "agent": "adapter",
            "artifact_id": "a-1",
            "run_id": "r-1",
            "inputs": {},
            "outputs": {"band_gap": 1.1},
            "metadata": {},
        },
    ]


def test_record_and_get_provenance_roundtrip(backend):
    count = backend.record_provenance("arc-sess", _entries())
    assert count == 2

    stored = backend.get_provenance("arc-sess")
    assert len(stored) == 2
    assert stored[0]["action"] == "start"
    assert stored[1]["run_id"] == "r-1"
    assert stored[1]["outputs"] == {"band_gap": 1.1}


def test_get_provenance_isolated_by_session(backend):
    backend.record_provenance("sess-a", _entries())
    backend.record_provenance("sess-b", _entries()[:1])
    assert len(backend.get_provenance("sess-a")) == 2
    assert len(backend.get_provenance("sess-b")) == 1
    assert backend.get_provenance("sess-c") == []


def test_record_provenance_skips_non_dict_entries(backend):
    count = backend.record_provenance("s", [{"action": "ok"}, "junk", 42])
    assert count == 1


@pytest.fixture
def client(tmp_path):
    app = create_results_service(
        backend="sqlite",
        db_path=str(tmp_path / "results.db"),
        require_auth=False,
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_provenance_endpoint_roundtrip(client):
    resp = client.post(
        "/provenance",
        json={"session_id": "arc-sess", "entries": _entries()},
    )
    assert resp.status_code == 201
    assert resp.get_json()["count"] == 2

    resp = client.get("/provenance/arc-sess")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 2
    assert body["entries"][0]["action"] == "start"


def test_provenance_endpoint_validates_payload(client):
    assert client.post("/provenance", json={}).status_code == 400
    assert client.post(
        "/provenance", json={"session_id": "s", "entries": "nope"},
    ).status_code == 400
