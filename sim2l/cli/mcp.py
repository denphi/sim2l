"""CLI commands for the optional sim2l MCP server."""

import click


@click.group()
def mcp():
    """Run sim2l MCP tools for agent clients."""


@mcp.command("serve")
@click.option(
    "--transport",
    default="stdio",
    show_default=True,
    help="MCP transport passed to FastMCP, commonly stdio for local clients.",
)
@click.option("--catalog-url", default=None, help="Catalog service URL.")
@click.option("--results-url", default=None, help="Results service URL.")
@click.option("--cache-url", default=None, help="Cache service URL.")
@click.option("--timeout", default=30.0, show_default=True, help="HTTP timeout in seconds.")
def serve(transport, catalog_url, results_url, cache_url, timeout):
    """Start the sim2l MCP server."""

    from sim2l.mcp.server import run_server

    run_server(
        transport=transport,
        catalog_url=catalog_url,
        results_url=results_url,
        cache_url=cache_url,
        timeout=timeout,
    )
