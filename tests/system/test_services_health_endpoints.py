#!/usr/bin/env python3
"""
System health checks for running sim2l services.

These tests verify that each service exposes a healthy `/health` endpoint.
They are integration checks and will be skipped if the service is not running.
"""

from __future__ import annotations

import pytest
import requests


SERVICES = [
    ("cache", "http://localhost:8001"),
    ("catalog", "http://localhost:8002"),
    ("results", "http://localhost:8003"),
]


def _get_health_payload(base_url: str) -> dict:
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
    except requests.exceptions.ConnectionError:
        pytest.skip(f"Service not reachable at {base_url}. Start it with ./start_services.sh")
    except requests.exceptions.RequestException as exc:
        pytest.fail(f"Unexpected network error for {base_url}: {exc}")

    assert response.status_code == 200, (
        f"Health endpoint failed for {base_url}. "
        f"Expected HTTP 200, got {response.status_code}: {response.text}"
    )
    return response.json()


@pytest.mark.parametrize(
    "service_name,base_url",
    SERVICES,
    ids=[service_name for service_name, _ in SERVICES],
)
def test_health_endpoint_reports_healthy_status(service_name: str, base_url: str):
    """Check that each service reports status=healthy on `/health`."""
    payload = _get_health_payload(base_url)
    assert payload.get("status") == "healthy", (
        f"{service_name} returned an unexpected health payload: {payload}"
    )


@pytest.mark.parametrize(
    "service_name,base_url",
    SERVICES,
    ids=[f"{service_name}-backend-field" for service_name, _ in SERVICES],
)
def test_health_endpoint_includes_backend_information(service_name: str, base_url: str):
    """Check that health payload includes backend information for observability."""
    payload = _get_health_payload(base_url)
    assert "backend" in payload, f"{service_name} health payload is missing 'backend': {payload}"
