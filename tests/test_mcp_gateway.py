from unittest.mock import Mock, patch

import pytest

from sim2l.mcp.gateway import Sim2LMCPGateway


def _response(status=200, body=None):
    response = Mock()
    response.status_code = status
    response.json.return_value = body if body is not None else {}
    if status >= 400:
        response.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    else:
        response.raise_for_status.return_value = None
    return response


def test_login_stores_per_service_tokens():
    gateway = Sim2LMCPGateway(
        catalog_url="http://catalog",
        results_url="http://results",
        cache_url="http://cache",
    )

    def post(url, **kwargs):
        service = url.split("//", 1)[1].split("/", 1)[0]
        return _response(body={"token": f"{service}-token", "username": "admin"})

    with patch("requests.post", side_effect=post):
        result = gateway.login("admin", "secret")

    assert result["success"] is True
    assert gateway.tokens.values == {
        "catalog": "catalog-token",
        "results": "results-token",
        "cache": "cache-token",
    }


def test_search_results_forwards_results_token():
    gateway = Sim2LMCPGateway(results_url="http://results")
    gateway.tokens.values["results"] = "results-token"

    with patch(
        "requests.post",
        return_value=_response(body={"results": [{"execution_id": "run-1"}]}),
    ) as post:
        rows = gateway.search_results(simulation_name="thermal", limit=3)

    assert rows == [{"execution_id": "run-1"}]
    _, kwargs = post.call_args
    assert kwargs["headers"]["X-Session-ID"] == "results-token"
    assert kwargs["json"]["simulation_name"] == "thermal"
    assert kwargs["json"]["limit"] == 3


def test_run_simulation_forwards_catalog_token():
    gateway = Sim2LMCPGateway(catalog_url="http://catalog")
    gateway.tokens.values["catalog"] = "catalog-token"

    with patch(
        "requests.post",
        return_value=_response(body={"success": True, "execution_id": "run-1"}),
    ) as post:
        result = gateway.run_simulation("thermal", params={"temperature": 300})

    assert result["execution_id"] == "run-1"
    _, kwargs = post.call_args
    assert kwargs["headers"]["X-Session-ID"] == "catalog-token"
    assert "X-Sim2L-Cache-Session-ID" not in kwargs["headers"]
    assert "X-Sim2L-Results-Session-ID" not in kwargs["headers"]
    assert kwargs["json"] == {
        "simulation_name": "thermal",
        "params": {"temperature": 300},
    }


def test_run_simulation_forwards_downstream_tokens():
    gateway = Sim2LMCPGateway(catalog_url="http://catalog")
    gateway.tokens.values.update({
        "catalog": "catalog-token",
        "cache": "cache-token",
        "results": "results-token",
    })

    with patch(
        "requests.post",
        return_value=_response(body={"success": True, "execution_id": "run-1"}),
    ) as post:
        gateway.run_simulation("thermal")

    _, kwargs = post.call_args
    assert kwargs["headers"]["X-Session-ID"] == "catalog-token"
    assert kwargs["headers"]["X-Sim2L-Cache-Session-ID"] == "cache-token"
    assert kwargs["headers"]["X-Sim2L-Results-Session-ID"] == "results-token"


def test_login_requires_credentials():
    gateway = Sim2LMCPGateway()
    with pytest.raises(ValueError, match="username and password"):
        gateway.login("", "")
