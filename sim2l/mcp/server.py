"""MCP server exposing sim2l service capabilities.

Install the optional MCP dependency before running this module:

    pip install "sim2l[mcp]"

The server is intentionally sim2l-owned. ARC and other agents consume these
tools through MCP; ARC-specific workflow control remains in ARC.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .gateway import Sim2LMCPGateway


def _import_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The optional MCP dependency is not installed. "
            'Install it with: pip install "sim2l[mcp]"'
        ) from exc
    return FastMCP


def create_server(
    *,
    catalog_url: Optional[str] = None,
    results_url: Optional[str] = None,
    cache_url: Optional[str] = None,
    timeout: float = 30.0,
):
    """Create a FastMCP server populated with sim2l tools."""

    FastMCP = _import_fastmcp()
    mcp = FastMCP("sim2l")
    gateway = Sim2LMCPGateway(
        catalog_url=catalog_url,
        results_url=results_url,
        cache_url=cache_url,
        timeout=timeout,
    )

    @mcp.tool()
    def sim2l_login(username: str, password: str) -> Dict[str, Any]:
        """Log in to sim2l services and store tokens for this MCP session."""

        return gateway.login(username, password)

    @mcp.tool()
    def sim2l_logout() -> Dict[str, Any]:
        """Forget sim2l service tokens held by this MCP server process."""

        return gateway.logout()

    @mcp.tool()
    def sim2l_search_simulations(
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = "active",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search the sim2l catalog for registered simulations."""

        return gateway.search_simulations(
            query=query,
            tags=tags,
            status=status,
            limit=limit,
        )

    @mcp.tool()
    def sim2l_get_simulation(
        name: str,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get catalog metadata for one registered simulation."""

        return gateway.get_simulation(name=name, version=version)

    @mcp.tool()
    def sim2l_run_simulation(
        simulation_name: str,
        params: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a registered sim2l simulation through the catalog service."""

        return gateway.run_simulation(
            simulation_name=simulation_name,
            params=params,
            version=version,
        )

    @mcp.tool()
    def sim2l_search_results(
        simulation_name: Optional[str] = None,
        simulation_version: Optional[str] = None,
        status: Optional[str] = None,
        input_filters: Optional[Dict[str, Any]] = None,
        output_filters: Optional[Dict[str, Any]] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search execution results by simulation and parameter filters."""

        return gateway.search_results(
            simulation_name=simulation_name,
            simulation_version=simulation_version,
            status=status,
            input_filters=input_filters,
            output_filters=output_filters,
            limit=limit,
        )

    @mcp.tool()
    def sim2l_list_results(limit: int = 25) -> List[Dict[str, Any]]:
        """List recent sim2l execution results."""

        return gateway.list_results(limit=limit)

    @mcp.tool()
    def sim2l_get_result(execution_id: str) -> Optional[Dict[str, Any]]:
        """Get one execution result by execution id."""

        return gateway.get_result(execution_id)

    return mcp


def run_server(
    *,
    transport: str = "stdio",
    catalog_url: Optional[str] = None,
    results_url: Optional[str] = None,
    cache_url: Optional[str] = None,
    timeout: float = 30.0,
) -> None:
    """Run the sim2l MCP server."""

    server = create_server(
        catalog_url=catalog_url,
        results_url=results_url,
        cache_url=cache_url,
        timeout=timeout,
    )
    server.run(transport=transport)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the sim2l MCP server.")
    parser.add_argument(
        "--transport",
        default="stdio",
        help="FastMCP transport, for example stdio or streamable-http.",
    )
    parser.add_argument("--catalog-url", default=None)
    parser.add_argument("--results-url", default=None)
    parser.add_argument("--cache-url", default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    run_server(
        transport=args.transport,
        catalog_url=args.catalog_url,
        results_url=args.results_url,
        cache_url=args.cache_url,
        timeout=args.timeout,
    )
