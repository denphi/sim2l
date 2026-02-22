#!/usr/bin/env python3
"""
PostgreSQL-specific tests for the catalog service backend.

These tests verify:
1. Catalog service starts with PostgreSQL backend and reports healthy.
2. Restarting against the same PostgreSQL catalog database remains healthy
   (guards against non-idempotent schema initialization issues).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


def _detect_postgres_base() -> str | None:
    """Return a reachable PostgreSQL base URL, else None."""
    candidates = [
        "postgresql://sim2l:sim2l_dev_password@localhost:5432",
        "postgresql://sim2l:sim2l_password@localhost:5432",
    ]
    try:
        import psycopg2
    except ImportError:
        return None

    for base in candidates:
        try:
            conn = psycopg2.connect(f"{base}/postgres", connect_timeout=2)
            conn.close()
            return base
        except Exception:
            continue
    return None


class TestCatalogPostgreSQLBackend(unittest.TestCase):
    """Integration tests for catalog service on PostgreSQL."""

    PORT = 18102

    @classmethod
    def setUpClass(cls):
        cls.pg_base = _detect_postgres_base()
        if not cls.pg_base:
            raise unittest.SkipTest("PostgreSQL not available for catalog backend tests")

        cls.db_url = f"{cls.pg_base}/sim2l_catalog"
        cls.runtime_dir = Path(tempfile.mkdtemp(prefix="sim2l-catalog-pg-test-"))

    def setUp(self):
        self.proc: subprocess.Popen | None = None
        self.log_stream = None
        self.log_path = self.runtime_dir / f"{self._testMethodName}.log"

    def tearDown(self):
        self._stop_service()

    def _start_service(self):
        cmd = [
            sys.executable,
            "-m",
            "sim2l.services.catalog_service",
            "--backend",
            "postgresql",
            "--db-url",
            self.db_url,
            "--no-auth",
            "--port",
            str(self.PORT),
        ]
        self.log_stream = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            cmd,
            stdout=self.log_stream,
            stderr=subprocess.STDOUT,
            env={**os.environ},
        )

    def _stop_service(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        if self.log_stream:
            self.log_stream.close()
            self.log_stream = None

    def _wait_for_health(self, timeout: int = 15) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{self.PORT}/health", timeout=2
                ) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                time.sleep(0.4)
        return False

    def _get_health(self) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{self.PORT}/health", timeout=5
            ) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                return exc.code, json.loads(payload)
            except Exception:
                return exc.code, {"error": payload.decode("utf-8", errors="replace")}

    def _read_log(self) -> str:
        if not self.log_path.exists():
            return ""
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def test_starts_with_postgresql_backend(self):
        self._start_service()
        self.assertTrue(
            self._wait_for_health(),
            f"Catalog service did not become healthy.\nLog:\n{self._read_log()}",
        )
        status, body = self._get_health()
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "healthy")
        self.assertEqual(body.get("backend"), "postgresql")

    def test_restart_is_idempotent_with_existing_schema(self):
        self._start_service()
        self.assertTrue(
            self._wait_for_health(),
            f"Initial startup failed.\nLog:\n{self._read_log()}",
        )
        self._stop_service()

        self._start_service()
        self.assertTrue(
            self._wait_for_health(),
            f"Restart startup failed.\nLog:\n{self._read_log()}",
        )
        status, body = self._get_health()
        self.assertEqual(status, 200)
        self.assertEqual(body.get("backend"), "postgresql")

        log_text = self._read_log()
        self.assertNotIn("DuplicateObject", log_text)
        self.assertNotIn("update_simulations_updated_at", log_text)
        self.assertNotIn("already exists", log_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
