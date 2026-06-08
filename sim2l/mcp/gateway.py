"""Gateway logic used by the sim2l MCP server.

This module intentionally does not import the MCP SDK. It wraps the existing
sim2l REST services with small, schema-friendly methods that can be registered
as MCP tools by :mod:`sim2l.mcp.server`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests


ServiceName = str


def _default_url(env_name: str, fallback: str) -> str:
    return os.environ.get(env_name, fallback).rstrip("/")


@dataclass
class Sim2LServiceTokens:
    """Process-local service tokens for one MCP server session."""

    values: Dict[ServiceName, str] = field(default_factory=dict)

    def headers(self, service: ServiceName) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = self.values.get(service)
        if token:
            headers["X-Session-ID"] = token
        return headers

    def clear(self) -> None:
        self.values.clear()


class Sim2LMCPGateway:
    """Small client facade exposed as MCP tools.

    The gateway talks to already-running sim2l services. Authentication is a
    first-class tool call: ``login`` exchanges username/password for per-service
    tokens, stores those tokens in-process, and subsequent calls forward the
    relevant ``X-Session-ID`` header.
    """

    def __init__(
        self,
        *,
        catalog_url: Optional[str] = None,
        results_url: Optional[str] = None,
        cache_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.catalog_url = (catalog_url or _default_url(
            "SIM2L_CATALOG_URL", "http://localhost:8002"
        )).rstrip("/")
        self.results_url = (results_url or _default_url(
            "SIM2L_RESULTS_URL", "http://localhost:8003"
        )).rstrip("/")
        self.cache_url = (cache_url or _default_url(
            "SIM2L_CACHE_URL", "http://localhost:8001"
        )).rstrip("/")
        self.timeout = timeout
        self.tokens = Sim2LServiceTokens()

    def _post(
        self,
        service: ServiceName,
        base_url: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        headers = self.tokens.headers(service)
        if extra_headers:
            headers.update({k: v for k, v in extra_headers.items() if v})
        response = requests.post(
            f"{base_url}{path}",
            json=payload or {},
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _get(
        self,
        service: ServiceName,
        base_url: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        response = requests.get(
            f"{base_url}{path}",
            params=params,
            headers=self.tokens.headers(service),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate to catalog, results, and cache services."""

        if not username or not password:
            raise ValueError("username and password are required")

        services = {
            "catalog": self.catalog_url,
            "results": self.results_url,
            "cache": self.cache_url,
        }
        logged_in: Dict[str, Dict[str, Any]] = {}
        errors: Dict[str, str] = {}

        for service, base_url in services.items():
            try:
                response = requests.post(
                    f"{base_url}/session/login",
                    json={"username": username, "password": password},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.json()
                token = body.get("token") or body.get("session_id")
                if not token:
                    raise RuntimeError("login response did not include a token")
                self.tokens.values[service] = token
                logged_in[service] = {
                    "username": body.get("username", username),
                    "expires_at": body.get("expires_at"),
                }
            except Exception as exc:
                errors[service] = str(exc)

        return {
            "success": bool(logged_in) and not errors,
            "logged_in": logged_in,
            "errors": errors,
        }

    def logout(self) -> Dict[str, Any]:
        """Forget process-local service tokens."""

        self.tokens.clear()
        return {"success": True}

    def search_simulations(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = "active",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if tags:
            params["tags"] = ",".join(tags)
        if status != "all":
            params["status"] = status
        data = self._get("catalog", self.catalog_url, "/simulations/search", params=params)
        return data if isinstance(data, list) else data.get("simulations", [])

    def get_simulation(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {"version": version} if version else None
        return self._get(
            "catalog",
            self.catalog_url,
            f"/simulations/{name}",
            params=params,
        )

    def run_simulation(
        self,
        simulation_name: str,
        params: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "simulation_name": simulation_name,
            "params": params or {},
        }
        if version:
            payload["version"] = version
        return self._post(
            "catalog",
            self.catalog_url,
            "/run",
            payload,
            extra_headers={
                "X-Sim2L-Cache-Session-ID": self.tokens.values.get("cache", ""),
                "X-Sim2L-Results-Session-ID": self.tokens.values.get("results", ""),
            },
        )

    def search_results(
        self,
        simulation_name: Optional[str] = None,
        simulation_version: Optional[str] = None,
        status: Optional[str] = None,
        input_filters: Optional[Dict[str, Any]] = None,
        output_filters: Optional[Dict[str, Any]] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        data = self._post(
            "results",
            self.results_url,
            "/search",
            {
                "simulation_name": simulation_name,
                "simulation_version": simulation_version,
                "status": status,
                "input_filters": input_filters or {},
                "output_filters": output_filters or {},
                "limit": limit,
            },
        )
        return data.get("results", [])

    def list_results(self, limit: int = 25) -> List[Dict[str, Any]]:
        return self.search_results(limit=limit)

    def get_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        response = requests.get(
            f"{self.results_url}/results/{execution_id}",
            headers=self.tokens.headers("results"),
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
