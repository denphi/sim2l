# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Pytest session bootstrap for local service-dependent tests.

Starts cache/catalog/results services on default ports when not already running.
Disable with: SIM2L_TEST_BOOTSTRAP_SERVICES=0
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import requests


_SERVICE_SPECS = [
    ("cache", "sim2l.services.cache_service", 8001),
    ("catalog", "sim2l.services.catalog_service", 8002),
    ("results", "sim2l.services.results_service", 8003),
]


def _truthy_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _is_service_healthy(port: int) -> bool:
    try:
        response = requests.get(f"http://localhost:{port}/health", timeout=1.5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _wait_for_service(port: int, timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_service_healthy(port):
            return True
        time.sleep(0.4)
    return False


def _read_tail(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return "(no log file)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return "(empty log)"
    return "\n".join(lines[-max_lines:])


@pytest.fixture(scope="session", autouse=True)
def bootstrap_local_services():
    """
    Start local services required by integration/system tests.

    Only starts services that are not already healthy.
    """
    if not _truthy_env("SIM2L_TEST_BOOTSTRAP_SERVICES", default=True):
        yield
        return

    runtime_dir = Path(tempfile.mkdtemp(prefix="sim2l-pytest-bootstrap-"))
    started: list[tuple[str, int, subprocess.Popen, object, Path]] = []

    try:
        for name, module, port in _SERVICE_SPECS:
            if _is_service_healthy(port):
                continue

            db_path = runtime_dir / f"{name}_{port}.db"
            log_path = runtime_dir / f"{name}_{port}.log"
            log_stream = open(log_path, "w", encoding="utf-8")
            cmd = [
                sys.executable,
                "-m",
                module,
                "--backend",
                "sqlite",
                "--db-path",
                str(db_path),
                "--no-auth",
                "--port",
                str(port),
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                env={**os.environ},
            )
            started.append((name, port, proc, log_stream, log_path))

            if not _wait_for_service(port):
                tail = _read_tail(log_path)
                raise RuntimeError(
                    f"Failed to bootstrap {name} service on port {port}.\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"Log tail:\n{tail}"
                )

        yield

    finally:
        for _, _, proc, log_stream, _ in started:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    proc.kill()
            log_stream.close()

        shutil.rmtree(runtime_dir, ignore_errors=True)
