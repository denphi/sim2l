"""
CLI commands for managing sim2l database services.

Provides commands to start, stop, and manage the cache and catalog services.
"""

import click
import subprocess
import sys
import os
import signal
from pathlib import Path
import json
import requests


@click.group()
def services():
    """Manage sim2l database services (cache, catalog)."""
    pass


@services.group()
def cache():
    """Manage cache service."""
    pass


@services.group()
def catalog():
    """Manage catalog service."""
    pass


@cache.command()
@click.option("--backend", type=click.Choice(["sqlite", "postgresql"]), default="sqlite")
@click.option("--db-path", type=click.Path(), default=None)
@click.option("--db-url", type=str, default=None)
@click.option("--host", default="0.0.0.0")
@click.option("--port", type=int, default=8001)
@click.option("--daemon", is_flag=True, help="Run as daemon")
def start(backend, db_path, db_url, host, port, daemon):
    """Start the cache service."""
    if db_path is None:
        db_path = str(Path.home() / ".sim2l" / "cache.db")

    cmd = [
        sys.executable,
        "-m",
        "sim2l.services.cache_service",
        "--backend",
        backend,
        "--host",
        host,
        "--port",
        str(port),
    ]

    if backend == "sqlite":
        cmd.extend(["--db-path", db_path])
    elif backend == "postgresql":
        if not db_url:
            click.echo("Error: --db-url required for PostgreSQL backend", err=True)
            sys.exit(1)
        cmd.extend(["--db-url", db_url])

    click.echo(f"Starting cache service on {host}:{port} with {backend} backend...")

    if daemon:
        # Run as daemon
        log_file = Path.home() / ".sim2l" / "logs" / "cache_service.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        pid_file = Path.home() / ".sim2l" / "cache_service.pid"

        with open(log_file, "a") as f:
            process = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True
            )

        with open(pid_file, "w") as f:
            f.write(str(process.pid))

        click.echo(f"Cache service started (PID: {process.pid})")
        click.echo(f"Logs: {log_file}")
    else:
        # Run in foreground
        subprocess.run(cmd)


@cache.command()
def stop():
    """Stop the cache service."""
    pid_file = Path.home() / ".sim2l" / "cache_service.pid"

    if not pid_file.exists():
        click.echo("Cache service is not running (no PID file)", err=True)
        sys.exit(1)

    with open(pid_file) as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Cache service stopped (PID: {pid})")
        pid_file.unlink()
    except ProcessLookupError:
        click.echo(f"Process {pid} not found (stale PID file)")
        pid_file.unlink()
    except Exception as e:
        click.echo(f"Error stopping service: {e}", err=True)
        sys.exit(1)


@cache.command()
@click.option("--url", default="http://localhost:8001")
def status(url):
    """Check cache service status."""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        data = response.json()

        if response.status_code == 200:
            click.echo(f"✓ Cache service is {data['status']}")
            click.echo(f"  Backend: {data['backend']}")
        else:
            click.echo(f"✗ Cache service is unhealthy: {data}")

    except requests.exceptions.RequestException as e:
        click.echo(f"✗ Cache service is not reachable: {e}", err=True)
        sys.exit(1)


@cache.command()
@click.option("--url", default="http://localhost:8001")
@click.option("--simulation-id", type=int, default=None)
def stats(url, simulation_id):
    """Get cache statistics."""
    try:
        params = {}
        if simulation_id:
            params["simulation_id"] = simulation_id

        response = requests.get(f"{url}/cache/stats", params=params, timeout=5)
        data = response.json()

        if response.status_code == 200:
            click.echo("Cache Statistics:")
            click.echo(f"  Total entries: {data.get('total_entries', 0)}")
            click.echo(f"  Total requests: {data.get('total_requests', 0)}")
            click.echo(f"  Cache hits: {data.get('cache_hits', 0)}")
            click.echo(f"  Cache misses: {data.get('cache_misses', 0)}")
            click.echo(f"  Hit rate: {data.get('hit_rate_percent', 0):.1f}%")
        else:
            click.echo(f"Error: {data}", err=True)
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@catalog.command("start")
@click.option("--backend", type=click.Choice(["sqlite", "postgresql"]), default="sqlite")
@click.option("--db-path", type=click.Path(), default=None)
@click.option("--db-url", type=str, default=None)
@click.option("--host", default="0.0.0.0")
@click.option("--port", type=int, default=8002)
@click.option("--daemon", is_flag=True, help="Run as daemon")
def catalog_start(backend, db_path, db_url, host, port, daemon):
    """Start the catalog service."""
    if db_path is None:
        db_path = str(Path.home() / ".sim2l" / "catalog.db")

    cmd = [
        sys.executable,
        "-m",
        "sim2l.services.catalog_service",
        "--backend",
        backend,
        "--host",
        host,
        "--port",
        str(port),
    ]

    if backend == "sqlite":
        cmd.extend(["--db-path", db_path])
    elif backend == "postgresql":
        if not db_url:
            click.echo("Error: --db-url required for PostgreSQL backend", err=True)
            sys.exit(1)
        cmd.extend(["--db-url", db_url])

    click.echo(f"Starting catalog service on {host}:{port} with {backend} backend...")

    if daemon:
        log_file = Path.home() / ".sim2l" / "logs" / "catalog_service.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        pid_file = Path.home() / ".sim2l" / "catalog_service.pid"

        with open(log_file, "a") as f:
            process = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True
            )

        with open(pid_file, "w") as f:
            f.write(str(process.pid))

        click.echo(f"Catalog service started (PID: {process.pid})")
        click.echo(f"Logs: {log_file}")
    else:
        subprocess.run(cmd)


@catalog.command("stop")
def catalog_stop():
    """Stop the catalog service."""
    pid_file = Path.home() / ".sim2l" / "catalog_service.pid"

    if not pid_file.exists():
        click.echo("Catalog service is not running (no PID file)", err=True)
        sys.exit(1)

    with open(pid_file) as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Catalog service stopped (PID: {pid})")
        pid_file.unlink()
    except ProcessLookupError:
        click.echo(f"Process {pid} not found (stale PID file)")
        pid_file.unlink()
    except Exception as e:
        click.echo(f"Error stopping service: {e}", err=True)
        sys.exit(1)


@catalog.command("status")
@click.option("--url", default="http://localhost:8002")
def catalog_status(url):
    """Check catalog service status."""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        data = response.json()

        if response.status_code == 200:
            click.echo(f"✓ Catalog service is {data['status']}")
            click.echo(f"  Backend: {data['backend']}")
            click.echo(f"  Simulations: {data.get('simulations', 0)}")
        else:
            click.echo(f"✗ Catalog service is unhealthy: {data}")

    except requests.exceptions.RequestException as e:
        click.echo(f"✗ Catalog service is not reachable: {e}", err=True)
        sys.exit(1)


@catalog.command("search")
@click.option("--url", default="http://localhost:8002")
@click.argument("query", required=False)
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--status", default="active")
@click.option("--limit", type=int, default=20)
def catalog_search(url, query, tags, status, limit):
    """Search for simulations in catalog."""
    try:
        params = {
            "status": status,
            "limit": limit,
        }
        if query:
            params["query"] = query
        if tags:
            params["tags"] = tags

        response = requests.get(f"{url}/simulations/search", params=params, timeout=10)

        if response.status_code == 200:
            results = response.json()

            if not results:
                click.echo("No simulations found")
                return

            click.echo(f"Found {len(results)} simulations:\n")

            for sim in results:
                click.echo(f"{sim['name']} v{sim['version']}")
                if sim.get("description"):
                    click.echo(f"  Description: {sim['description']}")
                if sim.get("author"):
                    click.echo(f"  Author: {sim['author']}")
                if sim.get("tags"):
                    click.echo(f"  Tags: {', '.join(sim['tags'])}")
                click.echo()
        else:
            click.echo(f"Error: {response.text}", err=True)
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@services.command()
@click.option("--cache-url", default="http://localhost:8001")
@click.option("--catalog-url", default="http://localhost:8002")
def health(cache_url, catalog_url):
    """Check health of all services."""
    click.echo("Checking service health...\n")

    # Check cache
    try:
        response = requests.get(f"{cache_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            click.echo(f"✓ Cache service: {data['status']} ({data['backend']})")
        else:
            click.echo(f"✗ Cache service: unhealthy")
    except Exception as e:
        click.echo(f"✗ Cache service: not reachable")

    # Check catalog
    try:
        response = requests.get(f"{catalog_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            click.echo(
                f"✓ Catalog service: {data['status']} "
                f"({data['backend']}, {data.get('simulations', 0)} sims)"
            )
        else:
            click.echo(f"✗ Catalog service: unhealthy")
    except Exception as e:
        click.echo(f"✗ Catalog service: not reachable")


@services.command()
@click.option("--cache/--no-cache", default=True)
@click.option("--catalog/--no-catalog", default=True)
@click.option("--cache-backend", type=click.Choice(["sqlite", "postgresql"]), default="sqlite")
@click.option("--catalog-backend", type=click.Choice(["sqlite", "postgresql"]), default="sqlite")
@click.option("--daemon", is_flag=True)
def start_all(cache, catalog, cache_backend, catalog_backend, daemon):
    """Start all services."""
    from .services import cache as cache_cmd
    from .services import catalog as catalog_cmd

    if cache:
        click.echo("Starting cache service...")
        cache_cmd.invoke(
            click.get_current_context(),
            backend=cache_backend,
            daemon=daemon,
        )

    if catalog:
        click.echo("Starting catalog service...")
        catalog_cmd.invoke(
            click.get_current_context(),
            backend=catalog_backend,
            daemon=daemon,
        )

    click.echo("\nAll services started!")


if __name__ == "__main__":
    services()
