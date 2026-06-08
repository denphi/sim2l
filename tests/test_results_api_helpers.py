import sim2l


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_results_uses_results_service_search(monkeypatch):
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response({"results": [{"execution_id": "run-1"}], "count": 1})

    monkeypatch.setattr("requests.post", fake_post)

    rows = sim2l.search_results(
        simulation_name="thermal_sim",
        simulation_version="1.0.0",
        status="completed",
        input_filters={"temperature": {"$gte": 350}},
        output_filters={"max_temperature": {"$lt": 500}},
        limit=5,
        base_url="http://results.example",
        session_id="session-1",
        timeout=7,
    )

    assert rows == [{"execution_id": "run-1"}]
    assert captured["url"] == "http://results.example/search"
    assert captured["headers"]["X-Session-ID"] == "session-1"
    assert captured["timeout"] == 7
    assert captured["json"] == {
        "simulation_name": "thermal_sim",
        "simulation_version": "1.0.0",
        "status": "completed",
        "input_filters": {"temperature": {"$gte": 350}},
        "output_filters": {"max_temperature": {"$lt": 500}},
        "limit": 5,
    }


def test_list_results_is_unfiltered_search(monkeypatch):
    captured = {}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Response({"results": [{"execution_id": "run-2"}], "count": 1})

    monkeypatch.setattr("requests.post", fake_post)

    rows = sim2l.list_results(
        simulation_name="thermal_sim",
        limit=3,
        base_url="http://localhost:8003",
    )

    assert rows == [{"execution_id": "run-2"}]
    assert captured["url"] == "http://localhost:8003/search"
    assert captured["json"]["simulation_name"] == "thermal_sim"
    assert captured["json"]["input_filters"] == {}
    assert captured["json"]["output_filters"] == {}
    assert captured["json"]["limit"] == 3

