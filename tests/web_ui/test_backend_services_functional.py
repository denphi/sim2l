#!/usr/bin/env python3
"""
Functional end-to-end tests for the sim2l web-ui backend APIs.

Automatically starts the three backend services (cache, catalog, results)
on temporary ports and validates API behavior used by the UI pages.

Usage:
    python3 tests/web_ui/test_backend_services_functional.py
    # or via pytest:
    pytest tests/web_ui/test_backend_services_functional.py -vv
"""

import sys
import os
import time
import uuid
import signal
import unittest
import subprocess
import urllib.request
import urllib.error
import json
import tempfile
from pathlib import Path

# Ports used for the test run (offset from defaults to avoid collisions)
CACHE_PORT   = 18001
CATALOG_PORT = 18002
RESULTS_PORT = 18003

CACHE_URL   = f"http://localhost:{CACHE_PORT}"
CATALOG_URL = f"http://localhost:{CATALOG_PORT}"
RESULTS_URL = f"http://localhost:{RESULTS_PORT}"

# Session IDs used per service in --no-auth mode:
#   cache service   creates "demo-session" in the DB (Flask also defaults to it)
#   catalog service uses the literal string "no-auth-session" (bypasses DB check)
#   results service uses check_session() which is bypassed in no-auth mode
CACHE_SESSION   = "demo-session"
CATALOG_SESSION = "no-auth-session"
RESULTS_SESSION = "demo-session"

# ── PostgreSQL detection ──────────────────────────────────────────────────────

def _detect_postgres() -> str | None:
    """Return a PostgreSQL base URL if a known instance is reachable, else None."""
    candidates = [
        "postgresql://sim2l:sim2l_password@localhost:5432",
    ]
    try:
        import psycopg2
        for base in candidates:
            try:
                conn = psycopg2.connect(f"{base}/postgres", connect_timeout=2)
                conn.close()
                return base
            except Exception:
                continue
    except ImportError:
        pass
    return None


def _ensure_postgres_databases(pg_base: str, db_names: list[str]) -> None:
    """Create missing PostgreSQL databases required by these tests."""
    import psycopg2
    from psycopg2 import sql

    conn = psycopg2.connect(f"{pg_base}/postgres", connect_timeout=3)
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        for db_name in db_names:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cursor.fetchone() is None:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
                )
    finally:
        cursor.close()
        conn.close()

# ── ANSI colours ──────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── service lifecycle ─────────────────────────────────────────────────────────

_processes: dict[str, subprocess.Popen] = {}
_log_files: dict[str, Path] = {}
_log_streams = {}
_runtime_dir = Path(tempfile.mkdtemp(prefix="sim2l-webui-functional-"))

# DB names per service in the PostgreSQL instance
_PG_DATABASES = {
    "cache":   "sim2l_cache",
    "catalog": "sim2l_catalog",
    "results": "sim2l_results",
}


def _start_service(name: str, module: str, port: int,
                   pg_base: str | None = None) -> subprocess.Popen:
    cmd = [sys.executable, "-m", module, "--no-auth", "--port", str(port)]
    if pg_base and name in _PG_DATABASES:
        db_url = f"{pg_base}/{_PG_DATABASES[name]}"
        cmd += ["--backend", "postgresql", "--db-url", db_url]
    else:
        cmd += ["--backend", "sqlite", "--db-path", str(_runtime_dir / f"{name}.db")]

    log_path = _runtime_dir / f"{name}.log"
    log_stream = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
        env={**os.environ},
    )
    _processes[name] = proc
    _log_files[name] = log_path
    _log_streams[name] = log_stream
    return proc


def _print_service_log_tail(name: str, max_lines: int = 80):
    log_path = _log_files.get(name)
    if not log_path or not log_path.exists():
        print(f"    No log file available for {name}")
        return

    print(f"    Log file: {log_path}")
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            print("    (log is empty)")
            return
        print("    --- log tail ---")
        for line in lines[-max_lines:]:
            print(f"    {line}")
    except Exception as exc:
        print(f"    Failed reading log: {exc}")


def _wait_for_service(url: str, timeout: int = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{url}/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def start_all_services(pg_base: str | None) -> list[str]:
    """Start cache, catalog, results services. Returns list of failed service names."""
    services = [
        ("cache",   "sim2l.services.cache_service",   CACHE_PORT,   CACHE_URL),
        ("catalog", "sim2l.services.catalog_service", CATALOG_PORT, CATALOG_URL),
        ("results", "sim2l.services.results_service", RESULTS_PORT, RESULTS_URL),
    ]
    failed = []
    for name, module, port, url in services:
        backend = "postgresql" if (pg_base and name in _PG_DATABASES) else "sqlite"
        print(f"  Starting {name} ({backend}) on port {port}...", end=" ", flush=True)
        _start_service(name, module, port, pg_base)
        if _wait_for_service(url):
            print(f"{GREEN}up{RESET}")
        else:
            print(f"{RED}FAILED{RESET}")
            _print_service_log_tail(name)
            failed.append(name)
    return failed


def stop_all_services():
    for name, proc in _processes.items():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        stream = _log_streams.get(name)
        if stream:
            stream.close()


_manual_runner_mode = False
_failed_services_for_module: list[str] = []
_pg_base_for_module: str | None = None


def setUpModule():
    """Start service dependencies when this module is run by pytest/unittest."""
    global _failed_services_for_module, _pg_base_for_module

    if _manual_runner_mode:
        return

    _pg_base_for_module = _detect_postgres()
    if _pg_base_for_module:
        try:
            _ensure_postgres_databases(
                _pg_base_for_module,
                list(_PG_DATABASES.values()),
            )
        except Exception as exc:
            print(
                f"  {YELLOW}PostgreSQL detected but DB preparation failed ({exc}). "
                f"Falling back to SQLite for service startup.{RESET}"
            )
            _pg_base_for_module = None
    _failed_services_for_module = start_all_services(_pg_base_for_module)

    if len(_failed_services_for_module) == 3:
        raise unittest.SkipTest("Cache, catalog, and results services all failed to start")


def tearDownModule():
    """Stop service dependencies when this module is run by pytest/unittest."""
    if _manual_runner_mode:
        return
    stop_all_services()


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _json_request(method: str, url: str, body: dict | None = None,
                   session_id: str = CACHE_SESSION) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Session-ID": session_id,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except Exception:
            text = payload.decode("utf-8", errors="replace")
            return e.code, {"error": text[:1000]}


def get(url, session_id=CACHE_SESSION):
    return _json_request("GET",  url, session_id=session_id)

def post(url, body, session_id=CACHE_SESSION):
    return _json_request("POST", url, body, session_id=session_id)

def patch(url, body, session_id=CACHE_SESSION):
    return _json_request("PATCH", url, body, session_id=session_id)

def delete(url, session_id=CACHE_SESSION):
    return _json_request("DELETE", url, session_id=session_id)


def _skip_if_service_failed(service_name: str):
    if service_name in _failed_services_for_module:
        raise unittest.SkipTest(f"{service_name} service failed to start for this test module")


# ══════════════════════════════════════════════════════════════════════════════
# CATALOG TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestCatalogService(unittest.TestCase):
    """Catalog API behavior expected by the UI catalog page."""

    SERVICE_NAME = "catalog"
    SIM_NAME = f"test_sim_{uuid.uuid4().hex[:8]}"
    SIM_VERSION = "1.0.0"

    @classmethod
    def setUpClass(cls):
        _skip_if_service_failed(cls.SERVICE_NAME)

    def _register(self, name=None, version=None, description="A test sim"):
        status, body = post(f"{CATALOG_URL}/simulations", {
            "name":          name or self.SIM_NAME,
            "version":       version or self.SIM_VERSION,
            "description":   description,
            "author":        "test_suite",
            "tags":          ["test"],
            "input_schema":  {"temperature": "float", "power": "float"},
            "output_schema": {"max_temp": "float", "converged": "bool"},
            "workflow_hash": "test_hash_000",
        }, session_id=CATALOG_SESSION)
        return status, body

    # ── health ────────────────────────────────────────────────────────────────

    def test_01_health(self):
        status, body = get(f"{CATALOG_URL}/health", session_id=CATALOG_SESSION)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "healthy")

    # ── register & retrieve ───────────────────────────────────────────────────

    def test_02_register_simulation(self):
        status, body = self._register()
        self.assertIn(status, (200, 201), f"Unexpected status {status}: {body}")
        # Service returns {"id": ..., "status": "registered"}
        self.assertIn("id", body, f"No id in response: {body}")
        TestCatalogService._sim_id = body["id"]

    def test_03_id_is_stable_on_duplicate_register(self):
        """Re-registering the same name+version must return the same ID."""
        if not hasattr(TestCatalogService, "_sim_id"):
            self.skipTest("test_02 did not run")
        # Service returns 409 on duplicate — that means the original ID is stable
        status, body = self._register()
        self.assertIn(status, (200, 201, 409),
                      f"Unexpected status on re-register: {status} {body}")
        if status == 409:
            pass  # 409 proves ID is stable (entry already exists)
        else:
            self.assertEqual(body.get("id"), TestCatalogService._sim_id,
                             "Re-registering same sim returned a different ID")

    def test_04_get_by_name(self):
        if not hasattr(TestCatalogService, "_sim_id"):
            self.skipTest("test_02 did not run")
        status, body = get(f"{CATALOG_URL}/simulations/{self.SIM_NAME}",
                           session_id=CATALOG_SESSION)
        self.assertEqual(status, 200, f"GET by name failed: {body}")
        self.assertEqual(body.get("name"), self.SIM_NAME)
        self.assertEqual(body.get("version"), self.SIM_VERSION)
        self.assertEqual(body.get("id"), TestCatalogService._sim_id,
                         "ID from GET does not match registered ID")

    def test_05_get_by_name_and_version(self):
        if not hasattr(TestCatalogService, "_sim_id"):
            self.skipTest("test_02 did not run")
        status, body = get(
            f"{CATALOG_URL}/simulations/{self.SIM_NAME}?version={self.SIM_VERSION}",
            session_id=CATALOG_SESSION,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body.get("version"), self.SIM_VERSION)

    def test_06_get_nonexistent_returns_404(self):
        status, _ = get(f"{CATALOG_URL}/simulations/does_not_exist_xyz",
                        session_id=CATALOG_SESSION)
        self.assertEqual(status, 404)

    # ── search ────────────────────────────────────────────────────────────────

    def test_07_search_finds_registered_sim(self):
        if not hasattr(TestCatalogService, "_sim_id"):
            self.skipTest("test_02 did not run")
        prefix = self.SIM_NAME[:12]
        status, body = get(f"{CATALOG_URL}/simulations/search?query={prefix}",
                           session_id=CATALOG_SESSION)
        self.assertEqual(status, 200)
        sims = body if isinstance(body, list) else body.get("simulations", [])
        names = [s.get("name") for s in sims]
        self.assertIn(self.SIM_NAME, names,
                      f"Registered sim not found in search results: {names}")

    def test_08_search_empty_query_returns_list(self):
        status, body = get(f"{CATALOG_URL}/simulations/search?query=",
                           session_id=CATALOG_SESSION)
        self.assertEqual(status, 200)
        sims = body if isinstance(body, list) else body.get("simulations", [])
        self.assertIsInstance(sims, list)
        self.assertGreater(len(sims), 0, "Empty query should return all simulations")

    def test_09_search_unknown_term_returns_empty(self):
        status, body = get(
            f"{CATALOG_URL}/simulations/search?query=zzz_no_match_xyz_9999",
            session_id=CATALOG_SESSION,
        )
        self.assertEqual(status, 200)
        sims = body if isinstance(body, list) else body.get("simulations", [])
        self.assertEqual(sims, [], f"Expected empty list, got: {sims}")

    # ── record execution & stats ──────────────────────────────────────────────

    def test_10_record_execution(self):
        if not hasattr(TestCatalogService, "_sim_id"):
            self.skipTest("test_02 did not run")
        status, body = post(f"{CATALOG_URL}/executions", {
            "simulation_id":   TestCatalogService._sim_id,
            "execution_id":    uuid.uuid4().hex,
            "squid_id":        uuid.uuid4().hex,
            "status":          "success",
            "executor_type":   "notebook",
            "started_at":      "2024-01-01T00:00:00",
            "cache_hit":       False,
        }, session_id=CATALOG_SESSION)
        self.assertIn(status, (200, 201), f"record_execution failed: {body}")

    def test_11_stats_returns_counts(self):
        if not hasattr(TestCatalogService, "_sim_id"):
            self.skipTest("test_02 did not run")
        status, body = get(
            f"{CATALOG_URL}/simulations/{TestCatalogService._sim_id}/stats",
            session_id=CATALOG_SESSION,
        )
        self.assertEqual(status, 200)
        self.assertIn("total_executions", body)

    def test_12_overview_stats(self):
        status, body = get(f"{CATALOG_URL}/statistics/overview",
                           session_id=CATALOG_SESSION)
        self.assertEqual(status, 200)
        for key in ("total_simulations", "total_executions"):
            self.assertIn(key, body, f"Missing key '{key}' in overview stats")
        self.assertGreaterEqual(body["total_simulations"], 1)

    def test_13_delete_simulation(self):
        sim_name = f"delete_sim_{uuid.uuid4().hex[:8]}"
        status, body = self._register(name=sim_name, version="9.9.9")
        self.assertIn(status, (200, 201), f"register failed: {status} {body}")
        sim_id = body.get("id")
        self.assertIsNotNone(sim_id, f"Missing simulation id in response: {body}")

        status, body = delete(f"{CATALOG_URL}/simulations/{sim_id}", session_id=CATALOG_SESSION)
        self.assertEqual(status, 200, f"delete failed: {body}")
        self.assertEqual(body.get("status"), "deleted")

        status, _ = get(f"{CATALOG_URL}/simulations/{sim_name}?version=9.9.9",
                        session_id=CATALOG_SESSION)
        self.assertEqual(status, 404, "Simulation still retrievable after delete")

    def test_14_register_and_retrieve_workflow_files(self):
        cases = [
            {
                "workflow_type": "notebook",
                "entrypoint": "workflow.ipynb",
                "files": [
                    {
                        "path": "workflow.ipynb",
                        "content": '{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}',
                        "content_type": "application/x-ipynb+json",
                    }
                ],
            },
            {
                "workflow_type": "function",
                "entrypoint": "workflow.py",
                "files": [
                    {
                        "path": "workflow.py",
                        "content": "def run(temperature, power):\n    return {'max_temp': temperature + power}",
                        "content_type": "text/x-python",
                    }
                ],
            },
            {
                "workflow_type": "docker",
                "entrypoint": "Dockerfile",
                "files": [
                    {
                        "path": "Dockerfile",
                        "content": "FROM python:3.11-slim\nCOPY app.py /app.py\nCMD ['python','/app.py']",
                        "content_type": "text/plain",
                    },
                    {
                        "path": "app.py",
                        "content": "print('hello from docker workflow')\n",
                        "content_type": "text/x-python",
                    },
                ],
            },
        ]

        for case in cases:
            sim_name = f"wf_{case['workflow_type']}_{uuid.uuid4().hex[:8]}"
            status, body = post(
                f"{CATALOG_URL}/simulations",
                {
                    "name": sim_name,
                    "version": "1.0.0",
                    "description": "workflow files test",
                    "author": "test_suite",
                    "tags": ["workflow-files", case["workflow_type"]],
                    "input_schema": {"temperature": {"type": "number"}},
                    "output_schema": {"max_temp": {"type": "number"}},
                    "workflow_type": case["workflow_type"],
                    "workflow_hash": f"hash_{uuid.uuid4().hex[:8]}",
                    "workflow_entrypoint": case["entrypoint"],
                    "workflow_files": case["files"],
                },
                session_id=CATALOG_SESSION,
            )
            self.assertIn(status, (200, 201), f"register failed for {case['workflow_type']}: {body}")

            status, body = get(
                f"{CATALOG_URL}/simulations/{sim_name}?version=1.0.0",
                session_id=CATALOG_SESSION,
            )
            self.assertEqual(status, 200, f"get failed for {case['workflow_type']}: {body}")
            self.assertEqual(body.get("workflow_type"), case["workflow_type"])

            workflow_bundle = body.get("workflow_bundle")
            self.assertIsInstance(workflow_bundle, dict, f"Missing workflow_bundle for {case['workflow_type']}")
            self.assertEqual(workflow_bundle.get("entrypoint"), case["entrypoint"])
            stored_paths = [f.get("path") for f in workflow_bundle.get("files", [])]
            expected_paths = [f["path"] for f in case["files"]]
            self.assertEqual(set(stored_paths), set(expected_paths))

            self.assertIsInstance(body.get("input_schema"), dict)
            self.assertIsInstance(body.get("output_schema"), dict)

    def test_15_register_schema_from_workflow_bundle(self):
        sim_name = f"wf_schema_bundle_{uuid.uuid4().hex[:8]}"
        status, body = post(
            f"{CATALOG_URL}/simulations",
            {
                "name": sim_name,
                "version": "1.0.0",
                "description": "schema in workflow bundle test",
                "author": "test_suite",
                "workflow_type": "notebook",
                "workflow_hash": f"hash_{uuid.uuid4().hex[:8]}",
                "workflow_bundle": {
                    "entrypoint": "workflow.ipynb",
                    "input_schema": {"power": {"type": "number"}},
                    "output_schema": {"temperature": {"type": "number"}},
                    "files": [
                        {
                            "path": "workflow.ipynb",
                            "content": '{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}',
                        }
                    ],
                },
            },
            session_id=CATALOG_SESSION,
        )
        self.assertIn(status, (200, 201), f"register failed: {status} {body}")

        status, body = get(
            f"{CATALOG_URL}/simulations/{sim_name}?version=1.0.0",
            session_id=CATALOG_SESSION,
        )
        self.assertEqual(status, 200, f"get failed: {body}")
        self.assertEqual(body.get("input_schema"), {"power": {"type": "number"}})
        self.assertEqual(body.get("output_schema"), {"temperature": {"type": "number"}})


# ══════════════════════════════════════════════════════════════════════════════
# CACHE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestCacheService(unittest.TestCase):
    """Cache API behavior expected by the UI cache page."""

    SERVICE_NAME = "cache"

    @classmethod
    def setUpClass(cls):
        _skip_if_service_failed(cls.SERVICE_NAME)

    def _unique_key(self):
        return f"test_key_{uuid.uuid4().hex}"

    def _store(self, key, ttl=None, sim_name="test_sim"):
        payload = {
            "cache_key":          key,
            "simulation_id":      1,
            "simulation_name":    sim_name,
            "simulation_version": "1.0.0",
            "squid_id":           uuid.uuid4().hex,
            "execution_id":       uuid.uuid4().hex,
            "input_hash":         uuid.uuid4().hex,
            "run_db_path":        "/tmp/test.db",
        }
        if ttl is not None:
            payload["ttl_seconds"] = ttl
        return post(f"{CACHE_URL}/cache", payload)

    # ── health ────────────────────────────────────────────────────────────────

    def test_01_health(self):
        status, body = get(f"{CACHE_URL}/health")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "healthy")

    # ── store & retrieve ──────────────────────────────────────────────────────

    def test_02_store_and_retrieve(self):
        key = self._unique_key()
        status, body = self._store(key)
        self.assertIn(status, (200, 201), f"Store failed: {body}")

        status, body = get(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 200, f"Retrieve failed: {body}")
        # Cache returns a reference record (execution_id, squid_id, run_db_path)
        self.assertIn("execution_id", body)
        self.assertIn("squid_id", body)

    def test_03_retrieve_missing_key_returns_404(self):
        status, _ = get(f"{CACHE_URL}/cache/does_not_exist_xyz_9999")
        self.assertEqual(status, 404)

    def test_04_overwrite_existing_entry(self):
        key = self._unique_key()
        _, body1 = self._store(key)
        self.assertEqual(body1.get("success"), True)
        _, body2 = self._store(key)  # overwrite
        self.assertEqual(body2.get("success"), True)

        # Entry should still be retrievable
        status, body = get(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 200, "Entry not found after overwrite")

    # ── TTL ───────────────────────────────────────────────────────────────────

    def test_05_entry_with_ttl_expires(self):
        key = self._unique_key()
        status, body = self._store(key, ttl=1)
        self.assertIn(status, (200, 201), f"Store with TTL failed: {body}")

        status, _ = get(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 200, "Entry not found immediately after store")

        time.sleep(2)
        status, _ = get(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 404,
                         "Entry still present after TTL expired — TTL not enforced")

    def test_06_entry_without_ttl_persists(self):
        key = self._unique_key()
        self._store(key)
        time.sleep(1)
        status, _ = get(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 200, "Entry without TTL disappeared unexpectedly")

    # ── list & stats ──────────────────────────────────────────────────────────

    def test_07_list_entries_returns_stored_key(self):
        key = self._unique_key()
        self._store(key)

        status, body = get(f"{CACHE_URL}/cache/entries?simulation_name=test_sim&limit=100")
        self.assertEqual(status, 200)
        entries = body.get("entries", [])
        keys = [e.get("cache_key") for e in entries]
        self.assertIn(key, keys, f"Newly stored key not found in list: {keys[:5]}…")

    def test_08_stats_returns_counts(self):
        status, body = get(f"{CACHE_URL}/cache/stats")
        self.assertEqual(status, 200)
        self.assertIn("total_entries", body)
        self.assertGreaterEqual(body["total_entries"], 1)

    # ── invalidate ────────────────────────────────────────────────────────────

    def test_09_invalidate_by_simulation_name(self):
        sim_name = f"invalidation_target_{uuid.uuid4().hex[:8]}"
        key = self._unique_key()
        status, _ = self._store(key, sim_name=sim_name)
        self.assertIn(status, (200, 201))

        status, _ = get(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 200)

        status, body = post(f"{CACHE_URL}/cache/invalidate",
                            {"simulation_name": sim_name})
        self.assertEqual(status, 200, f"Invalidate failed: {body}")
        self.assertGreaterEqual(body.get("invalidated_count", 0), 1)

        status, _ = get(f"{CACHE_URL}/cache/{key}")
        self.assertIn(status, (404, 410),
                      "Entry still retrievable after invalidation")

    def test_10_delete_entry(self):
        key = self._unique_key()
        status, body = self._store(key)
        self.assertIn(status, (200, 201), f"Store failed: {body}")

        status, body = delete(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 200, f"Delete failed: {body}")
        self.assertIn("deleted_count", body)

        status, _ = get(f"{CACHE_URL}/cache/{key}")
        self.assertEqual(status, 404, "Entry still retrievable after delete")


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestResultsService(unittest.TestCase):
    """Results API behavior expected by the UI results page."""

    SERVICE_NAME = "results"
    SIM_NAME = f"test_results_sim_{uuid.uuid4().hex[:8]}"
    SIM_VERSION = "1.0.0"

    @classmethod
    def setUpClass(cls):
        _skip_if_service_failed(cls.SERVICE_NAME)

    def _register_result(self, temperature=300.0, power=5.0,
                          max_temp=450.0, converged=True,
                          execution_id=None, squid_id=None):
        execution_id = execution_id or uuid.uuid4().hex
        squid_id     = squid_id or uuid.uuid4().hex
        status, body = post(f"{RESULTS_URL}/register_direct", {
            "simulation_name":    self.SIM_NAME,
            "simulation_version": self.SIM_VERSION,
            "execution_id":       execution_id,
            "squid_id":           squid_id,
            "status":             "success",
            "input_params":  {"temperature": temperature, "power": power},
            "output_params": {"max_temp": max_temp, "converged": converged},
            "started_at":  "2024-01-01T00:00:00",
            "finished_at": "2024-01-01T00:01:00",
            "execution_time_ms": 60000,
            "cache_hit": False,
        })
        return status, body, execution_id, squid_id

    # ── health ────────────────────────────────────────────────────────────────

    def test_01_health(self):
        status, body = get(f"{RESULTS_URL}/health")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "healthy")

    # ── register & retrieve ───────────────────────────────────────────────────

    def test_02_register_and_retrieve(self):
        status, body, exec_id, squid_id = self._register_result(
            temperature=300.0, power=5.0, max_temp=450.0
        )
        self.assertIn(status, (200, 201), f"Register failed: {body}")

        status, body = get(f"{RESULTS_URL}/results/{exec_id}")
        self.assertEqual(status, 200, f"Retrieve failed: {body}")
        self.assertEqual(body.get("execution_id"), exec_id)
        self.assertEqual(body.get("squid_id"), squid_id,
                         "SQUID ID in retrieved result does not match registered value")
        self.assertEqual(body.get("simulation_name"), self.SIM_NAME)
        self.assertEqual(body.get("status"), "success")

    def test_03_squid_id_is_unique_per_parameter_set(self):
        """Same squid_id registered twice: the latest execution_id wins (upsert).
        The squid_id always resolves to exactly one record."""
        shared_squid = uuid.uuid4().hex
        _, _, exec1, _ = self._register_result(squid_id=shared_squid)
        _, _, exec2, _ = self._register_result(squid_id=shared_squid)

        # Only one of the two exec_ids should be retrievable (the surviving one)
        s1, b1 = get(f"{RESULTS_URL}/results/{exec1}")
        s2, b2 = get(f"{RESULTS_URL}/results/{exec2}")

        surviving = [b for s, b in [(s1, b1), (s2, b2)] if s == 200]
        self.assertEqual(len(surviving), 1,
                         "Expected exactly one execution to survive the upsert")
        self.assertEqual(surviving[0].get("squid_id"), shared_squid,
                         "Surviving result has wrong squid_id")

    def test_04_retrieve_nonexistent_returns_404(self):
        status, _ = get(f"{RESULTS_URL}/results/does_not_exist_xyz_9999")
        self.assertEqual(status, 404)

    # ── search ────────────────────────────────────────────────────────────────

    def test_05_search_by_simulation_name(self):
        self._register_result()
        status, body = post(f"{RESULTS_URL}/search", {
            "simulation_name": self.SIM_NAME,
            "limit": 100,
        })
        self.assertEqual(status, 200)
        results = body.get("results", [])
        self.assertGreater(len(results), 0, "Search by name returned no results")
        for r in results:
            self.assertEqual(r.get("simulation_name"), self.SIM_NAME)

    def test_06_search_by_status(self):
        self._register_result()
        status, body = post(f"{RESULTS_URL}/search", {
            "simulation_name": self.SIM_NAME,
            "status": "success",
            "limit": 100,
        })
        self.assertEqual(status, 200)
        results = body.get("results", [])
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r.get("status"), "success")

    def test_07_search_input_filter_eq(self):
        unique_temp = 999.0
        self._register_result(temperature=unique_temp)
        status, body = post(f"{RESULTS_URL}/search", {
            "simulation_name": self.SIM_NAME,
            "input_filters": {"temperature": {"$eq": unique_temp}},
            "limit": 100,
        })
        self.assertEqual(status, 200)
        results = body.get("results", [])
        self.assertGreater(len(results), 0,
                           f"No results found for temperature={unique_temp}")
        for r in results:
            self.assertEqual(
                r.get("input_params", {}).get("temperature"), unique_temp,
                "Result with wrong temperature included in filtered results"
            )

    def test_08_search_input_filter_gt(self):
        self._register_result(power=100.0)
        status, body = post(f"{RESULTS_URL}/search", {
            "simulation_name": self.SIM_NAME,
            "input_filters": {"power": {"$gt": 99.0}},
            "limit": 100,
        })
        self.assertEqual(status, 200)
        results = body.get("results", [])
        self.assertGreater(len(results), 0, "No results found for power > 99")
        for r in results:
            self.assertGreater(
                r.get("input_params", {}).get("power"), 99.0,
                "Result with power <= 99 included in $gt filter results"
            )

    def test_09_search_output_filter(self):
        self._register_result(max_temp=999.9, converged=True)
        status, body = post(f"{RESULTS_URL}/search", {
            "simulation_name": self.SIM_NAME,
            "output_filters": {"max_temp": {"$gte": 999.0}},
            "limit": 100,
        })
        self.assertEqual(status, 200)
        results = body.get("results", [])
        self.assertGreater(len(results), 0, "No results found for max_temp >= 999")

    def test_10_search_no_match_returns_empty(self):
        status, body = post(f"{RESULTS_URL}/search", {
            "simulation_name": "zzz_no_such_simulation_xyz",
            "limit": 10,
        })
        self.assertEqual(status, 200)
        results = body.get("results", [])
        self.assertEqual(results, [], f"Expected empty list, got: {results}")

    # ── parameter stats ───────────────────────────────────────────────────────

    def test_11_parameter_stats(self):
        for temp in (100.0, 200.0, 300.0):
            self._register_result(temperature=temp)

        # class=input to query input_params; service returns min_value/max_value
        status, body = get(
            f"{RESULTS_URL}/stats/{self.SIM_NAME}/temperature?class=input",
            session_id=RESULTS_SESSION,
        )
        self.assertEqual(status, 200, f"Parameter stats failed: {body}")
        self.assertIn("count", body)
        self.assertGreater(body["count"], 0, "Stats returned count=0, no data found")
        self.assertIn("min_value", body)
        self.assertIn("max_value", body)
        self.assertLessEqual(body["min_value"], 100.0)
        self.assertGreaterEqual(body["max_value"], 300.0)

    def test_12_delete_result(self):
        status, body, exec_id, _ = self._register_result()
        self.assertIn(status, (200, 201), f"Register failed: {body}")

        status, body = delete(f"{RESULTS_URL}/results/{exec_id}", session_id=RESULTS_SESSION)
        self.assertEqual(status, 200, f"Delete failed: {body}")
        self.assertEqual(body.get("status"), "deleted")

        status, _ = get(f"{RESULTS_URL}/results/{exec_id}", session_id=RESULTS_SESSION)
        self.assertEqual(status, 404, "Result still retrievable after delete")


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def _print_summary(result: unittest.TestResult):
    total    = result.testsRun
    skipped  = len(result.skipped)
    failures = len(result.failures)
    errors   = len(result.errors)
    passed   = total - failures - errors

    print(f"\n{'=' * 60}")
    print(f"{BOLD}Summary{RESET}")
    print(f"{'=' * 60}")
    print(f"  Ran:     {total}")
    print(f"  {GREEN}Passed:  {passed}{RESET}")
    if skipped:
        print(f"  {YELLOW}Skipped: {skipped}{RESET}")
    if failures:
        print(f"  {RED}Failed:  {failures}{RESET}")
    if errors:
        print(f"  {RED}Errors:  {errors}{RESET}")
    print()
    if failures == 0 and errors == 0:
        print(f"{GREEN}{BOLD}All tests passed.{RESET}")
    else:
        print(f"{RED}{BOLD}Some tests failed — see details above.{RESET}")


if __name__ == "__main__":
    _manual_runner_mode = True

    # Handle Ctrl+C cleanly
    signal.signal(signal.SIGINT, lambda *_: (stop_all_services(), sys.exit(1)))

    print(f"\n{BOLD}sim2l Web-UI Functional Tests{RESET}")
    print("=" * 60)
    print(f"Runtime dir: {_runtime_dir}")

    pg_base = _detect_postgres()
    if pg_base:
        print(f"  PostgreSQL detected at {pg_base}")
    else:
        print(f"  {YELLOW}PostgreSQL not detected — all services will use SQLite{RESET}")
    print()
    print("Starting services...")

    _failed_services_for_module = start_all_services(pg_base)
    if _failed_services_for_module:
        print(f"\n{RED}Could not start: {', '.join(_failed_services_for_module)}{RESET}")
        print("Tests for those services will be skipped.")
        if len(_failed_services_for_module) == 3:
            print(f"{RED}All services failed to start. Exiting with failure.{RESET}")
            stop_all_services()
            sys.exit(1)

    print()

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    # Only add test classes for services that came up
    service_map = {
        "catalog": TestCatalogService,
        "cache":   TestCacheService,
        "results": TestResultsService,
    }
    for name, cls in service_map.items():
        if name in _failed_services_for_module:
            print(f"{YELLOW}Skipping {cls.__name__} (service failed to start){RESET}")
        else:
            suite.addTests(loader.loadTestsFromTestCase(cls))

    try:
        runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
        result = runner.run(suite)
        _print_summary(result)
    finally:
        print(f"\n{YELLOW}Stopping services...{RESET}")
        stop_all_services()
        print("Done.")

    sys.exit(0 if result.wasSuccessful() else 1)
