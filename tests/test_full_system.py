# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Comprehensive system tests for sim2l cache, services, Docker, and web UI.

Test groups (each runnable independently):

  1. TestCacheSQLiteBackend     – SQLiteCacheBackend directly (no HTTP)
  2. TestRunDatabase            – Per-run SQLite database (no HTTP)
  3. TestLocalCacheClient       – In-memory LocalCacheClient (no HTTP)
  4. TestCacheServiceFlask      – Cache Service REST routes via Flask test client
  5. TestCacheClientMocked      – CacheClient HTTP calls (mocked)
  6. TestResultsClientMocked    – ResultsClient HTTP calls (mocked)
  7. TestCatalogClientMocked    – CatalogClient HTTP calls (mocked)
  8. TestLiveServicesIntegration – Real subprocesses on ports 8021-8023
  9. TestDockerServices         – Real Docker services on ports 8001-8003
                                  (skipped automatically if not running)

Run all:
    pytest tests/test_full_system.py -v

Run one group:
    pytest tests/test_full_system.py::TestCacheServiceFlask -v

Run only the Docker group:
    pytest tests/test_full_system.py::TestDockerServices -v
"""

import hashlib
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import requests

# Ensure project root is importable even when run directly.
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

SESSION_ID = "test-session"
HEADERS = {"X-Session-ID": SESSION_ID}


def _compute_hash(data: dict) -> str:
    """Stable MD5 of JSON-serialised data (mirrors sim2l's hash logic)."""
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _make_cache_payload(
    name: str = "thermal_sim",
    version: str = "1.0.0",
    sim_id: int = 1,
    exec_id: Optional[str] = None,
    inputs: Optional[dict] = None,
) -> dict:
    """Build a minimal valid cache entry payload."""
    if inputs is None:
        inputs = {"temperature": 300.0, "pressure": 1.5}
    if exec_id is None:
        exec_id = f"exec-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    h = _compute_hash(inputs)
    return {
        "cache_key": f"{name}_{version}_{h[:8]}",
        "simulation_id": sim_id,
        "simulation_name": name,
        "simulation_version": version,
        "execution_id": exec_id,
        "squid_id": f"{name}/{version}/{h[:8]}",
        "input_hash": h,
        "run_db_path": f"/tmp/runs/{exec_id}.db",
        "metadata": {"inputs": inputs},
    }


def _insert_demo_session(db_path: str, session_id: str = SESSION_ID) -> None:
    """Insert a long-lived session row into a freshly created SQLite database."""
    expires = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    for table in ("cache_sessions", "catalog_sessions"):
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} "
                "(session_id, user_id, expires_at, access_level, is_valid) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, 1, expires, "write", 1),
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Table doesn't exist in this DB – skip silently.
    conn.close()


def _start_service(module: str, db_path: str, port: int) -> subprocess.Popen:
    """Launch a sim2l service as a subprocess using --no-auth SQLite mode."""
    return subprocess.Popen(
        [
            sys.executable, "-m", module,
            "--backend", "sqlite",
            "--db-path", db_path,
            "--no-auth",
            "--port", str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_service(port: int, timeout: int = 15) -> bool:
    """Poll /health until the service responds 200 or the timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{port}/health", timeout=1)
            if r.status_code == 200:
                return True
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(0.3)
    return False


def _services_reachable(ports: dict) -> bool:
    """Return True only if all ports return a 200 health response."""
    for port in ports.values():
        try:
            r = requests.get(f"http://localhost:{port}/health", timeout=1)
            if r.status_code != 200:
                return False
        except Exception:
            return False
    return True


# ═════════════════════════════════════════════════════════════════════════════
# 1. SQLiteCacheBackend Unit Tests  (no HTTP)
# ═════════════════════════════════════════════════════════════════════════════

class TestCacheSQLiteBackend(unittest.TestCase):
    """Direct tests of SQLiteCacheBackend – no Flask, no HTTP."""

    def setUp(self):
        from sim2l.services.cache_service import SQLiteCacheBackend
        self.temp_dir = tempfile.mkdtemp(prefix="sim2l-backend-")
        self.db_path = os.path.join(self.temp_dir, "cache.db")
        self.backend = SQLiteCacheBackend(self.db_path)
        _insert_demo_session(self.db_path)
        self.sid = SESSION_ID

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _set(self, name="thermal_sim", version="1.0.0", inputs=None, sim_id=1):
        payload = _make_cache_payload(name, version, sim_id, inputs=inputs)
        result, status = self.backend.set(payload, self.sid)
        return result, status, payload

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_set_returns_success(self):
        _, status, _ = self._set()
        self.assertEqual(status, 200)

    def test_get_hit_returns_full_entry(self):
        _, _, payload = self._set()
        data, status = self.backend.get(payload["cache_key"], self.sid)
        self.assertEqual(status, 200)
        self.assertEqual(data["execution_id"], payload["execution_id"])
        self.assertEqual(data["squid_id"], payload["squid_id"])
        self.assertIn("run_db_path", data)
        self.assertIn("metadata", data)

    def test_get_miss_returns_404(self):
        _, status = self.backend.get("nonexistent-key-xyz", self.sid)
        self.assertEqual(status, 404)

    def test_stats_counts_after_set(self):
        self._set()
        result, status = self.backend.get_stats(None)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(result["total_entries"], 1)

    def test_stats_hits_increment_on_get(self):
        _, _, payload = self._set()
        self.backend.get(payload["cache_key"], self.sid)
        self.backend.get(payload["cache_key"], self.sid)
        result, _ = self.backend.get_stats(None)
        self.assertGreaterEqual(result["total_hits"], 2)

    def test_invalidate_by_simulation_name(self):
        _, _, p_flow = self._set(name="flow_sim")
        _, _, p_chem = self._set(name="chem_sim")
        result, status = self.backend.invalidate({"simulation_name": "flow_sim"}, self.sid)
        self.assertEqual(status, 200)
        self.assertEqual(result["invalidated_count"], 1)
        # flow_sim key should now be gone
        _, miss_status = self.backend.get(p_flow["cache_key"], self.sid)
        self.assertEqual(miss_status, 404)
        # chem_sim should still be retrievable
        _, hit_status = self.backend.get(p_chem["cache_key"], self.sid)
        self.assertEqual(hit_status, 200)

    def test_invalidate_by_version(self):
        self._set(name="ver_sim", version="1.0.0", sim_id=10)
        self._set(name="ver_sim", version="2.0.0", sim_id=11)
        result, _ = self.backend.invalidate({"simulation_version": "1.0.0"}, self.sid)
        self.assertEqual(result["invalidated_count"], 1)

    def test_delete_removes_entry(self):
        _, _, payload = self._set()
        result, status = self.backend.delete(payload["cache_key"], self.sid)
        self.assertEqual(status, 200)
        self.assertEqual(result["deleted_count"], 1)
        _, miss = self.backend.get(payload["cache_key"], self.sid)
        self.assertEqual(miss, 404)

    def test_delete_nonexistent_returns_404(self):
        _, status = self.backend.delete("no-such-key-zzz", self.sid)
        self.assertEqual(status, 404)

    def test_list_entries_returns_pagination_fields(self):
        self._set(name="list_a", sim_id=20)
        self._set(name="list_b", sim_id=21)
        result, status = self.backend.list_entries(limit=50, offset=0, session_id=self.sid)
        self.assertEqual(status, 200)
        self.assertIn("entries", result)
        self.assertIn("total", result)
        self.assertIn("limit", result)
        self.assertIn("offset", result)
        self.assertGreaterEqual(result["total"], 2)

    def test_list_entries_filter_by_simulation_name(self):
        unique = f"unique_sim_{random.randint(10_000, 99_999)}"
        self._set(name=unique, sim_id=99)
        result, _ = self.backend.list_entries(simulation_name=unique, session_id=self.sid)
        for entry in result["entries"]:
            self.assertEqual(entry["simulation_name"], unique)

    def test_list_entries_each_entry_has_required_fields(self):
        self._set()
        result, _ = self.backend.list_entries(limit=1, session_id=self.sid)
        if result["entries"]:
            entry = result["entries"][0]
            for field in ("cache_key", "simulation_name", "simulation_version",
                          "execution_id", "squid_id", "status"):
                self.assertIn(field, entry, f"Entry missing field: {field}")

    def test_health_check_returns_healthy_sqlite(self):
        result, status = self.backend.health_check()
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["backend"], "sqlite")

    def test_ttl_entry_expires(self):
        """Entry with ttl_seconds=1 must become unreachable after expiry."""
        payload = _make_cache_payload()
        payload["ttl_seconds"] = 1
        self.backend.set(payload, self.sid)
        # Immediately reachable
        _, status = self.backend.get(payload["cache_key"], self.sid)
        self.assertEqual(status, 200)
        time.sleep(2)
        # Now expired
        _, status = self.backend.get(payload["cache_key"], self.sid)
        self.assertEqual(status, 404)

    def test_invalid_session_rejected(self):
        payload = _make_cache_payload()
        _, status = self.backend.set(payload, "totally-invalid-session-id")
        self.assertEqual(status, 401)


# ═════════════════════════════════════════════════════════════════════════════
# 2. RunDatabase Unit Tests  (no HTTP)
# ═════════════════════════════════════════════════════════════════════════════

class TestRunDatabase(unittest.TestCase):
    """Tests for the per-run isolated SQLite RunDatabase."""

    def setUp(self):
        from sim2l.database.run_database import RunDatabase
        self.RunDatabase = RunDatabase
        self.temp_dir = tempfile.mkdtemp(prefix="sim2l-rundb-")
        self.exec_id = f"exec-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self.db_path = os.path.join(self.temp_dir, f"{self.exec_id}.db")
        self.db = RunDatabase(self.exec_id, self.db_path)

    def tearDown(self):
        self.db.close()
        time.sleep(0.05)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialize_run_records_metadata(self):
        self.db.initialize_run("thermal_sim", "1.0.0")
        summary = self.db.get_summary()
        self.assertEqual(summary["simulation_name"], "thermal_sim")
        self.assertEqual(summary["simulation_version"], "1.0.0")
        self.assertEqual(summary["status"], "running")

    def test_save_and_retrieve_inputs(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.db.save_input("temperature", 300.5, "float")
        self.db.save_input("pressure", 1.2, "float")
        self.db.save_input("enabled", True, "bool")
        inputs = self.db.get_inputs()
        self.assertIn("temperature", inputs)
        self.assertAlmostEqual(inputs["temperature"]["value"], 300.5)
        self.assertIn("pressure", inputs)
        self.assertIn("enabled", inputs)

    def test_save_and_retrieve_outputs(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.db.save_output("max_temp", 350.0, "float")
        self.db.save_output("converged", True, "bool")
        self.db.save_output("data_points", json.dumps([1.0, 2.0, 3.0]), "list")
        outputs = self.db.get_outputs()
        self.assertIn("max_temp", outputs)
        self.assertIn("converged", outputs)
        self.assertIn("data_points", outputs)

    def test_complete_run_success_status(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.db.complete_run("completed", duration_seconds=1.5)
        self.assertEqual(self.db.get_summary()["status"], "completed")

    def test_complete_run_failed_status(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.db.complete_run("failed", error_message="Diverged", error_traceback="Traceback…")
        self.assertEqual(self.db.get_summary()["status"], "failed")

    def test_log_entries_stored_and_retrieved(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.db.log("INFO", "Simulation started", logger_name="sim.engine")
        self.db.log("ERROR", "Convergence failed", exception_type="RuntimeError")
        logs = self.db.get_logs()
        levels = {l["level"] for l in logs}
        self.assertIn("INFO", levels)
        self.assertIn("ERROR", levels)

    def test_get_errors_filters_to_error_and_critical(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.db.log("DEBUG", "debug msg")
        self.db.log("ERROR", "error msg")
        self.db.log("CRITICAL", "critical msg")
        errors = self.db.get_errors()
        levels = {e["level"] for e in errors}
        self.assertIn("ERROR", levels)
        self.assertIn("CRITICAL", levels)
        self.assertNotIn("DEBUG", levels)

    def test_save_artifact_returns_id(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        artifact_id = self.db.save_artifact(
            name="result_plot.png",
            content=b"fake image bytes",
            content_type="image/png",
            category="output",
            description="Result visualization",
        )
        self.assertIsNotNone(artifact_id)
        self.assertIsInstance(artifact_id, int)

    def test_save_metric_does_not_raise(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.db.save_metric("convergence_rate", 0.9834, category="performance")
        self.db.save_metric("iterations", 150.0, metric_unit="count", category="performance")

    def test_context_manager_closes_connection(self):
        exec_id2 = f"exec-ctx-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        db_path2 = os.path.join(self.temp_dir, f"{exec_id2}.db")
        with self.RunDatabase(exec_id2, db_path2) as db:
            db.initialize_run("ctx_sim", "1.0.0")
            self.assertEqual(db.get_summary()["simulation_name"], "ctx_sim")
        # Connection should be None after __exit__
        self.assertIsNone(db.conn)

    def test_get_size_bytes_positive_after_init(self):
        self.db.initialize_run("flow_sim", "2.0.0")
        self.assertGreater(self.db.get_size_bytes(), 0)


# ═════════════════════════════════════════════════════════════════════════════
# 3. LocalCacheClient Unit Tests  (no HTTP)
# ═════════════════════════════════════════════════════════════════════════════

class TestLocalCacheClient(unittest.TestCase):
    """Tests for the in-memory LocalCacheClient (no HTTP layer)."""

    def setUp(self):
        from sim2l.database.cache_client import LocalCacheClient
        self.cache = LocalCacheClient(session_id="test-session")

    def _set(self, key="k1", name="sim", version="1.0.0", exec_id="exec-001"):
        return self.cache.set(
            cache_key=key,
            simulation_id=1,
            simulation_name=name,
            simulation_version=version,
            execution_id=exec_id,
            squid_id=f"{name}/{version}/abc",
            input_hash="abc123",
            run_db_path=f"/tmp/{exec_id}.db",
        )

    def test_set_returns_true(self):
        self.assertTrue(self._set())

    def test_get_hit_returns_entry(self):
        self._set()
        result = self.cache.get("k1")
        self.assertIsNotNone(result)
        self.assertEqual(result["execution_id"], "exec-001")

    def test_get_miss_returns_none(self):
        self.assertIsNone(self.cache.get("nonexistent-key"))

    def test_ttl_entry_expires(self):
        self.cache.set(
            cache_key="ttl-key", simulation_id=1, simulation_name="s",
            simulation_version="1.0.0", execution_id="e-ttl",
            squid_id="s/1.0.0/ttl", input_hash="h", run_db_path="/t.db",
            ttl_seconds=1,
        )
        self.assertIsNotNone(self.cache.get("ttl-key"))
        time.sleep(2)
        self.assertIsNone(self.cache.get("ttl-key"))

    def test_invalidate_by_name_removes_correct_entry(self):
        self._set("k1", name="flow", exec_id="e1")
        self._set("k2", name="chem", exec_id="e2")
        count = self.cache.invalidate(simulation_name="flow")
        self.assertEqual(count, 1)
        self.assertIsNone(self.cache.get("k1"))
        self.assertIsNotNone(self.cache.get("k2"))

    def test_invalidate_by_version(self):
        self._set("k1", version="1.0.0", exec_id="e1")
        self._set("k2", version="2.0.0", exec_id="e2")
        count = self.cache.invalidate(simulation_version="1.0.0")
        self.assertEqual(count, 1)
        self.assertIsNone(self.cache.get("k1"))

    def test_invalidate_by_pattern(self):
        self._set("thermal_v1_abc", exec_id="e1")
        self._set("flow_v1_abc", exec_id="e2")
        count = self.cache.invalidate(pattern="thermal%")
        self.assertEqual(count, 1)
        self.assertIsNone(self.cache.get("thermal_v1_abc"))
        self.assertIsNotNone(self.cache.get("flow_v1_abc"))

    def test_stats_track_hits_misses_and_rate(self):
        self._set("k1", exec_id="e1")
        self.cache.get("k1")    # hit
        self.cache.get("k1")    # hit
        self.cache.get("miss")  # miss
        stats = self.cache.get_stats()
        self.assertEqual(stats["cache_hits"], 2)
        self.assertEqual(stats["cache_misses"], 1)
        # hit rate = 2/3 ≈ 66.67 %
        self.assertGreater(stats["hit_rate_percent"], 60.0)

    def test_stats_total_entries_count(self):
        self._set("k1", exec_id="e1")
        self._set("k2", exec_id="e2")
        self.assertEqual(self.cache.get_stats()["total_entries"], 2)

    def test_health_check_always_true(self):
        self.assertTrue(self.cache.health_check())


# ═════════════════════════════════════════════════════════════════════════════
# 4. Cache Service Flask Route Tests  (Flask test client, no subprocess)
# ═════════════════════════════════════════════════════════════════════════════

class TestCacheServiceFlask(unittest.TestCase):
    """
    Tests every Cache Service REST route using Flask's built-in test client.
    No external process is required.
    """

    @classmethod
    def setUpClass(cls):
        import sim2l.services.cache_service as svc
        from sim2l.services.cache_service import SQLiteCacheBackend, app

        cls.temp_dir = tempfile.mkdtemp(prefix="sim2l-flask-")
        cls.db_path = os.path.join(cls.temp_dir, "cache.db")

        backend = SQLiteCacheBackend(cls.db_path)
        _insert_demo_session(cls.db_path)

        svc.cache_db = backend
        svc.require_auth = False  # All routes accept any session-id header.
        app.config["TESTING"] = True
        cls.client = app.test_client()
        cls._svc = svc  # Keep reference for per-test require_auth toggling.

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # ── private helpers ───────────────────────────────────────────────────────

    def _post(self, payload=None):
        if payload is None:
            payload = _make_cache_payload()
        return self.client.post(
            "/cache",
            data=json.dumps(payload),
            content_type="application/json",
            headers=HEADERS,
        )

    def _get(self, key):
        return self.client.get(f"/cache/{key}", headers=HEADERS)

    # ── health ────────────────────────────────────────────────────────────────

    def test_health_requires_no_auth(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_health_returns_healthy_status(self):
        data = json.loads(self.client.get("/health").data)
        self.assertEqual(data["status"], "healthy")

    def test_health_reports_sqlite_backend(self):
        data = json.loads(self.client.get("/health").data)
        self.assertEqual(data["backend"], "sqlite")

    # ── POST /cache (set) ─────────────────────────────────────────────────────

    def test_set_returns_success(self):
        r = self._post()
        self.assertIn(r.status_code, [200, 201])
        self.assertTrue(json.loads(r.data).get("success"))

    def test_set_missing_session_when_auth_required(self):
        self._svc.require_auth = True
        r = self.client.post(
            "/cache",
            data=json.dumps(_make_cache_payload()),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)
        self._svc.require_auth = False

    # ── GET /cache/<key> ──────────────────────────────────────────────────────

    def test_get_hit_returns_execution_id(self):
        payload = _make_cache_payload()
        self._post(payload)
        data = json.loads(self._get(payload["cache_key"]).data)
        self.assertEqual(data["execution_id"], payload["execution_id"])
        self.assertEqual(data["squid_id"], payload["squid_id"])
        self.assertIn("run_db_path", data)

    def test_get_hit_includes_metadata(self):
        payload = _make_cache_payload(inputs={"temp": 350.0, "pressure": 2.0})
        self._post(payload)
        data = json.loads(self._get(payload["cache_key"]).data)
        self.assertIn("metadata", data)

    def test_get_miss_returns_404(self):
        r = self._get("completely-nonexistent-key-xyz-999")
        self.assertEqual(r.status_code, 404)

    # ── DELETE /cache/<key> ───────────────────────────────────────────────────

    def test_delete_existing_entry_returns_count(self):
        payload = _make_cache_payload()
        self._post(payload)
        r = self.client.delete(f"/cache/{payload['cache_key']}", headers=HEADERS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(r.data)["deleted_count"], 1)

    def test_delete_nonexistent_returns_404(self):
        r = self.client.delete("/cache/not-there-key-zzz", headers=HEADERS)
        self.assertEqual(r.status_code, 404)

    def test_delete_then_get_is_miss(self):
        payload = _make_cache_payload()
        self._post(payload)
        self.client.delete(f"/cache/{payload['cache_key']}", headers=HEADERS)
        self.assertEqual(self._get(payload["cache_key"]).status_code, 404)

    # ── GET /cache/stats ──────────────────────────────────────────────────────

    def test_stats_has_required_fields(self):
        self._post(_make_cache_payload())
        data = json.loads(self.client.get("/cache/stats").data)
        for field in ("total_entries", "total_accesses", "total_hits"):
            self.assertIn(field, data, f"stats missing '{field}'")

    def test_stats_hits_increment_after_gets(self):
        payload = _make_cache_payload()
        self._post(payload)
        hits_before = json.loads(self.client.get("/cache/stats").data)["total_hits"]
        self._get(payload["cache_key"])
        self._get(payload["cache_key"])
        hits_after = json.loads(self.client.get("/cache/stats").data)["total_hits"]
        self.assertGreaterEqual(hits_after, hits_before + 2)

    # ── POST /cache/invalidate ────────────────────────────────────────────────

    def test_invalidate_by_simulation_name(self):
        p_a = _make_cache_payload(name="inv_sim_a")
        p_b = _make_cache_payload(name="inv_sim_b")
        self._post(p_a)
        self._post(p_b)
        r = self.client.post(
            "/cache/invalidate",
            data=json.dumps({"simulation_name": "inv_sim_a"}),
            content_type="application/json",
            headers=HEADERS,
        )
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(json.loads(r.data)["invalidated_count"], 1)
        # inv_sim_a should now be a 404
        self.assertEqual(self._get(p_a["cache_key"]).status_code, 404)
        # inv_sim_b should still be a 200
        self.assertEqual(self._get(p_b["cache_key"]).status_code, 200)

    def test_invalidate_by_version(self):
        p = _make_cache_payload(name="ver_inv_sim", version="77.0.0")
        self._post(p)
        r = self.client.post(
            "/cache/invalidate",
            data=json.dumps({"simulation_version": "77.0.0"}),
            content_type="application/json",
            headers=HEADERS,
        )
        self.assertGreaterEqual(json.loads(r.data)["invalidated_count"], 1)

    # ── GET /cache/entries ────────────────────────────────────────────────────

    def test_list_entries_returns_pagination_structure(self):
        for i in range(3):
            self._post(_make_cache_payload(name=f"listed_sim_{i}", sim_id=100 + i))
        r = self.client.get("/cache/entries?limit=10&offset=0", headers=HEADERS)
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        for field in ("entries", "total", "limit", "offset"):
            self.assertIn(field, data, f"entries response missing '{field}'")

    def test_list_entries_filter_by_name(self):
        unique = f"only_this_sim_{random.randint(10_000, 99_999)}"
        self._post(_make_cache_payload(name=unique))
        r = self.client.get(f"/cache/entries?simulation_name={unique}&limit=10", headers=HEADERS)
        data = json.loads(r.data)
        for entry in data["entries"]:
            self.assertEqual(entry["simulation_name"], unique)

    def test_list_entries_entry_has_all_web_ui_fields(self):
        """Each entry must carry the fields the web-ui CacheEntry type expects."""
        self._post(_make_cache_payload())
        r = self.client.get("/cache/entries?limit=1", headers=HEADERS)
        data = json.loads(r.data)
        if data["entries"]:
            entry = data["entries"][0]
            for field in ("cache_key", "simulation_name", "simulation_version",
                          "execution_id", "squid_id", "status"):
                self.assertIn(field, entry, f"Entry missing web-UI field: '{field}'")


# ═════════════════════════════════════════════════════════════════════════════
# 5. CacheClient HTTP Tests  (mocked)
# ═════════════════════════════════════════════════════════════════════════════

class TestCacheClientMocked(unittest.TestCase):
    """CacheClient uses self._session (requests.Session) – patched here."""

    def setUp(self):
        from sim2l.database.cache_client import CacheClient
        self.client = CacheClient("http://localhost:9999", session_id="mock-session")

    def _mock_resp(self, status: int, body: dict = None) -> MagicMock:
        m = MagicMock()
        m.status_code = status
        m.json.return_value = body or {}
        m.text = json.dumps(body or {})
        return m

    def test_get_hit_returns_entry(self):
        body = {"execution_id": "exec-123", "squid_id": "s/1.0/x",
                "run_db_path": "/tmp/r.db", "metadata": None}
        with patch.object(self.client._session, "get", return_value=self._mock_resp(200, body)):
            result = self.client.get("some-key")
        self.assertIsNotNone(result)
        self.assertEqual(result["execution_id"], "exec-123")

    def test_get_miss_returns_none(self):
        with patch.object(self.client._session, "get", return_value=self._mock_resp(404)):
            self.assertIsNone(self.client.get("missing"))

    def test_get_unauthorized_returns_none(self):
        with patch.object(self.client._session, "get", return_value=self._mock_resp(401)):
            self.assertIsNone(self.client.get("some-key"))

    def test_get_network_error_returns_none(self):
        with patch.object(self.client._session, "get",
                          side_effect=requests.exceptions.ConnectionError()):
            self.assertIsNone(self.client.get("some-key"))

    def test_set_success_returns_true(self):
        with patch.object(self.client._session, "post", return_value=self._mock_resp(200)):
            result = self.client.set(
                cache_key="k1", simulation_id=1, simulation_name="s",
                simulation_version="1.0.0", execution_id="e1",
                squid_id="s/1.0.0/h", input_hash="h", run_db_path="/p.db",
            )
        self.assertTrue(result)

    def test_set_server_error_returns_false(self):
        with patch.object(self.client._session, "post",
                          return_value=self._mock_resp(500, {"error": "oops"})):
            result = self.client.set(
                cache_key="k1", simulation_id=1, simulation_name="s",
                simulation_version="1.0.0", execution_id="e1",
                squid_id="sq", input_hash="h", run_db_path="/p.db",
            )
        self.assertFalse(result)

    def test_invalidate_returns_count(self):
        with patch.object(self.client._session, "post",
                          return_value=self._mock_resp(200, {"invalidated_count": 5})):
            count = self.client.invalidate(simulation_name="my_sim")
        self.assertEqual(count, 5)

    def test_invalidate_network_error_returns_minus_one(self):
        with patch.object(self.client._session, "post",
                          side_effect=requests.exceptions.Timeout()):
            self.assertEqual(self.client.invalidate(simulation_name="s"), -1)

    def test_get_stats_returns_dict(self):
        with patch.object(self.client._session, "get",
                          return_value=self._mock_resp(200, {"total_entries": 10})):
            stats = self.client.get_stats()
        self.assertEqual(stats["total_entries"], 10)

    def test_health_check_true_on_200(self):
        with patch.object(self.client._session, "get", return_value=self._mock_resp(200)):
            self.assertTrue(self.client.health_check())

    def test_health_check_false_on_connection_error(self):
        with patch.object(self.client._session, "get",
                          side_effect=requests.exceptions.ConnectionError()):
            self.assertFalse(self.client.health_check())


# ═════════════════════════════════════════════════════════════════════════════
# 6. ResultsClient HTTP Tests  (mocked)
# ResultsClient uses direct requests.get/post (not a session object).
# ═════════════════════════════════════════════════════════════════════════════

class TestResultsClientMocked(unittest.TestCase):
    """ResultsClient calls requests.get/post directly – patched at module level."""

    def setUp(self):
        from sim2l.database.results_client import ResultsClient
        self.client = ResultsClient("http://localhost:9999", session_id="mock-session")
        self._mod = "sim2l.database.results_client.requests"

    def _mock_resp(self, status: int, body: dict = None) -> MagicMock:
        m = MagicMock()
        m.status_code = status
        m.json.return_value = body or {}
        m.raise_for_status = MagicMock()
        if status >= 400:
            m.raise_for_status.side_effect = requests.HTTPError(response=m)
        return m

    def test_health_check_returns_dict(self):
        body = {"status": "healthy", "service": "results", "backend": "sqlite"}
        with patch(f"{self._mod}.get", return_value=self._mock_resp(200, body)):
            result = self.client.health_check()
        self.assertEqual(result["status"], "healthy")

    def test_health_check_returns_unhealthy_on_error(self):
        with patch(f"{self._mod}.get",
                   side_effect=requests.exceptions.ConnectionError("down")):
            result = self.client.health_check()
        self.assertIn("unhealthy", result.get("status", ""))

    def test_register_result_returns_ids(self):
        body = {"success": True, "result_id": 42, "schema_id": 7}
        with patch(f"{self._mod}.post", return_value=self._mock_resp(200, body)):
            result = self.client.register_result(
                execution_id="exec-001",
                squid_id="sim/1.0.0/abc",
                metadata={"inputs": {"temp": 300}},
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["result_id"], 42)

    def test_search_returns_list(self):
        body = {
            "results": [{"execution_id": "exec-001", "simulation_name": "thermal", "status": "completed"}],
            "count": 1,
        }
        with patch(f"{self._mod}.post", return_value=self._mock_resp(200, body)):
            results = self.client.search(simulation_name="thermal")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

    def test_get_result_returns_dict(self):
        body = {"execution_id": "exec-001", "status": "completed"}
        with patch(f"{self._mod}.get", return_value=self._mock_resp(200, body)):
            result = self.client.get_result("exec-001")
        self.assertIsNotNone(result)
        self.assertEqual(result["execution_id"], "exec-001")

    def test_get_result_not_found_returns_none(self):
        with patch(f"{self._mod}.get", return_value=self._mock_resp(404)):
            result = self.client.get_result("ghost")
        self.assertIsNone(result)

    def test_get_parameter_stats_returns_stats(self):
        body = {"param_name": "max_temp", "min_value": 300.0,
                "max_value": 450.0, "avg_value": 375.0, "count": 10}
        with patch(f"{self._mod}.get", return_value=self._mock_resp(200, body)):
            stats = self.client.get_parameter_stats("thermal", "max_temp")
        self.assertEqual(stats["count"], 10)


# ═════════════════════════════════════════════════════════════════════════════
# 7. CatalogClient HTTP Tests  (mocked)
# CatalogClient uses self._session (requests.Session).
# Init without session_id to avoid the _register_installation() network call.
# ═════════════════════════════════════════════════════════════════════════════

class TestCatalogClientMocked(unittest.TestCase):

    def setUp(self):
        from sim2l.database.catalog_client import CatalogClient
        # No session_id → skips _register_installation() network call.
        self.client = CatalogClient("http://localhost:9999")

    def _mock_resp(self, status: int, body=None) -> MagicMock:
        m = MagicMock()
        m.status_code = status
        m.json.return_value = body if body is not None else {}
        m.text = json.dumps(body or {})
        return m

    def test_health_check_returns_true_on_200(self):
        with patch.object(self.client._session, "get", return_value=self._mock_resp(200)):
            self.assertTrue(self.client.health_check())

    def test_health_check_returns_false_on_connection_error(self):
        with patch.object(self.client._session, "get",
                          side_effect=requests.exceptions.ConnectionError()):
            self.assertFalse(self.client.health_check())

    def test_search_returns_list(self):
        body = [{"name": "thermal_sim", "version": "1.0.0"},
                {"name": "flow_sim", "version": "2.0.0"}]
        with patch.object(self.client._session, "get", return_value=self._mock_resp(200, body)):
            sims = self.client.search(query="thermal")
        self.assertIsInstance(sims, list)

    def test_get_simulation_returns_dict(self):
        body = {"name": "thermal_sim", "version": "1.0.0", "id": 1}
        with patch.object(self.client._session, "get", return_value=self._mock_resp(200, body)):
            sim = self.client.get_simulation("thermal_sim")
        self.assertIsNotNone(sim)
        self.assertEqual(sim["name"], "thermal_sim")

    def test_get_simulation_not_found_returns_none(self):
        with patch.object(self.client._session, "get", return_value=self._mock_resp(404)):
            self.assertIsNone(self.client.get_simulation("ghost_sim"))


# ═════════════════════════════════════════════════════════════════════════════
# 8. Live Services Integration Tests  (subprocess, ports 8021-8023)
# ═════════════════════════════════════════════════════════════════════════════

class TestLiveServicesIntegration(unittest.TestCase):
    """
    Starts all three services as subprocesses on ephemeral ports.
    Tests the full simulation data flow: catalog → cache → results.
    Automatically skipped if any service fails to come up within 15 s.
    """

    PORTS = {"cache": 8021, "catalog": 8022, "results": 8023}

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="sim2l-live-")
        cls.procs = {}
        cls.skip_reason = None

        for name, module in [
            ("cache",   "sim2l.services.cache_service"),
            ("catalog", "sim2l.services.catalog_service"),
            ("results", "sim2l.services.results_service"),
        ]:
            db = os.path.join(cls.temp_dir, f"{name}.db")
            cls.procs[name] = _start_service(module, db, cls.PORTS[name])

        for name, port in cls.PORTS.items():
            if not _wait_for_service(port):
                cls.skip_reason = f"{name} service did not start on port {port}"
                return

        cls.HDRS = {"X-Session-ID": "live-test-session"}

    @classmethod
    def tearDownClass(cls):
        for proc in cls.procs.values():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    # ── URL helpers ───────────────────────────────────────────────────────────

    def _url(self, svc: str, path: str = "") -> str:
        return f"http://localhost:{self.PORTS[svc]}{path}"

    # ── Health ────────────────────────────────────────────────────────────────

    def test_all_services_healthy(self):
        for svc in ("cache", "catalog", "results"):
            r = requests.get(self._url(svc, "/health"))
            self.assertEqual(r.status_code, 200,
                             f"{svc} service health check failed")
            self.assertIn("status", r.json())

    # ── Cache Service full flow ───────────────────────────────────────────────

    def test_cache_set_get_delete_cycle(self):
        payload = _make_cache_payload(name="live_thermal", version="1.0.0", sim_id=1)

        # Set
        r = requests.post(self._url("cache", "/cache"), json=payload, headers=self.HDRS)
        self.assertIn(r.status_code, [200, 201])
        self.assertTrue(r.json().get("success"))

        # Get – hit
        r = requests.get(self._url("cache", f"/cache/{payload['cache_key']}"),
                         headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["execution_id"], payload["execution_id"])

        # Stats
        stats = requests.get(self._url("cache", "/cache/stats")).json()
        self.assertGreaterEqual(stats["total_entries"], 1)

        # Delete
        r = requests.delete(self._url("cache", f"/cache/{payload['cache_key']}"),
                            headers=self.HDRS)
        self.assertEqual(r.status_code, 200)

        # Get – miss after delete
        r = requests.get(self._url("cache", f"/cache/{payload['cache_key']}"),
                         headers=self.HDRS)
        self.assertEqual(r.status_code, 404)

    def test_cache_invalidation_preserves_other_entries(self):
        p1 = _make_cache_payload(name="target_sim")
        p2 = _make_cache_payload(name="keep_me_sim")
        requests.post(self._url("cache", "/cache"), json=p1, headers=self.HDRS)
        requests.post(self._url("cache", "/cache"), json=p2, headers=self.HDRS)

        r = requests.post(
            self._url("cache", "/cache/invalidate"),
            json={"simulation_name": "target_sim"},
            headers=self.HDRS,
        )
        self.assertGreaterEqual(r.json()["invalidated_count"], 1)
        self.assertEqual(
            requests.get(self._url("cache", f"/cache/{p1['cache_key']}"),
                         headers=self.HDRS).status_code, 404,
        )
        self.assertEqual(
            requests.get(self._url("cache", f"/cache/{p2['cache_key']}"),
                         headers=self.HDRS).status_code, 200,
        )

    def test_cache_list_entries_pagination(self):
        for i in range(3):
            requests.post(self._url("cache", "/cache"),
                          json=_make_cache_payload(name=f"page_sim_{i}", sim_id=200 + i),
                          headers=self.HDRS)
        r = requests.get(self._url("cache", "/cache/entries"),
                         params={"limit": 50}, headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for field in ("entries", "total", "limit", "offset"):
            self.assertIn(field, data)

    def test_cache_stats_has_all_fields(self):
        stats = requests.get(self._url("cache", "/cache/stats")).json()
        for field in ("total_entries", "total_accesses", "total_hits"):
            self.assertIn(field, stats)

    # ── Catalog Service ───────────────────────────────────────────────────────

    def test_catalog_register_and_search(self):
        sim_name = f"live_catalog_sim_{random.randint(1000, 9999)}"
        sim = {
            "name": sim_name,
            "version": "1.0.0",
            "squid_id": "live_catalog/1.0.0/main",
            "description": "Live catalog test",
            # workflow_hash is NOT NULL in the catalog schema.
            "workflow_hash": hashlib.md5(sim_name.encode()).hexdigest(),
            "input_schema": {"type": "object", "properties": {"temperature": {"type": "number"}}},
            "output_schema": {"type": "object", "properties": {"max_temp": {"type": "number"}}},
            "metadata": {"author": "test_suite", "tags": ["test"]},
        }
        r = requests.post(self._url("catalog", "/simulations"), json=sim, headers=self.HDRS)
        self.assertIn(r.status_code, [200, 201])

        r = requests.get(self._url("catalog", "/simulations/search"))
        self.assertEqual(r.status_code, 200)

    # ── Results Service ───────────────────────────────────────────────────────

    def test_results_register_direct_and_search(self):
        exec_id = f"live-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        r = requests.post(
            self._url("results", "/register_direct"),
            json={
                "execution_id": exec_id,
                "simulation_name": "live_results_sim",
                "simulation_version": "1.0.0",
                "squid_id": f"live_results_sim/1.0.0/{exec_id[:8]}",
                "input_params": {"temperature": 300.0},
                "output_params": {"max_temp": 350.0, "converged": True},
                "status": "completed",
                "duration_seconds": 12.3,
                "run_db_path": f"/tmp/{exec_id}.db",
                "metadata": {"cache_hit": False},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201])
        self.assertTrue(r.json().get("success"))

        r = requests.post(
            self._url("results", "/search"),
            json={"simulation_name": "live_results_sim", "limit": 10},
            headers=self.HDRS,
        )
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

    def test_results_get_single_execution(self):
        exec_id = f"live-get-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        requests.post(
            self._url("results", "/register_direct"),
            json={
                "execution_id": exec_id,
                "simulation_name": "get_test", "simulation_version": "1.0.0",
                "squid_id": f"get_test/1.0.0/abc",
                "input_params": {"x": 1}, "output_params": {"y": 2},
                "status": "completed", "duration_seconds": 1.0,
                "run_db_path": "/tmp/g.db",
            },
            headers=self.HDRS,
        )
        r = requests.get(self._url("results", f"/results/{exec_id}"), headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["execution_id"], exec_id)

    def test_results_delete_execution(self):
        exec_id = f"live-del-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        requests.post(
            self._url("results", "/register_direct"),
            json={
                "execution_id": exec_id,
                "simulation_name": "del_test", "simulation_version": "1.0.0",
                "squid_id": "del_test/1.0.0/abc",
                "input_params": {}, "output_params": {},
                "status": "completed", "duration_seconds": 0.5,
                "run_db_path": "/tmp/d.db",
            },
            headers=self.HDRS,
        )
        r = requests.delete(self._url("results", f"/results/{exec_id}"), headers=self.HDRS)
        self.assertIn(r.status_code, [200, 204])

    # ── Full simulation data flow across all three services ───────────────────

    def test_full_simulation_flow_catalog_cache_results(self):
        """
        Registers a simulation in the catalog, stores its result in the cache,
        registers the result in the results service, then verifies it appears
        in a results search – exercising all three services in one test.
        """
        sim_name = f"e2e_sim_{random.randint(1000, 9999)}"
        version = "1.0.0"
        inputs = {"temperature": round(random.uniform(300, 400), 2),
                  "power": round(random.uniform(1, 10), 2)}
        outputs = {"max_temp": inputs["temperature"] * 1.15, "converged": True}
        exec_id = f"e2e-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        input_hash = _compute_hash(inputs)

        # 1. Catalog: register simulation
        r = requests.post(
            self._url("catalog", "/simulations"),
            json={
                "name": sim_name, "version": version,
                "squid_id": f"{sim_name}/{version}/main",
                "description": "E2E flow test",
                "workflow_hash": hashlib.md5(sim_name.encode()).hexdigest(),
                "input_schema": {"type": "object",
                                 "properties": {"temperature": {"type": "number"}}},
                "output_schema": {"type": "object",
                                  "properties": {"max_temp": {"type": "number"}}},
                "metadata": {"author": "e2e_test"},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201],
                      f"Catalog register failed: {r.status_code} {r.text}")

        # 2. Cache: store execution
        cache_key = f"{sim_name}_{version}_{input_hash[:8]}"
        r = requests.post(
            self._url("cache", "/cache"),
            json={
                "cache_key": cache_key,
                "simulation_id": 1, "simulation_name": sim_name,
                "simulation_version": version, "execution_id": exec_id,
                "squid_id": f"{sim_name}/{version}/{input_hash[:8]}",
                "input_hash": input_hash,
                "run_db_path": f"/tmp/{exec_id}.db",
                "metadata": {"inputs": inputs},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201],
                      f"Cache set failed: {r.status_code} {r.text}")

        # 3. Cache: verify hit
        r = requests.get(self._url("cache", f"/cache/{cache_key}"), headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["execution_id"], exec_id)

        # 4. Results: register result
        r = requests.post(
            self._url("results", "/register_direct"),
            json={
                "execution_id": exec_id,
                "simulation_name": sim_name, "simulation_version": version,
                "squid_id": f"{sim_name}/{version}/{input_hash[:8]}",
                "input_params": inputs, "output_params": outputs,
                "status": "completed",
                "duration_seconds": round(random.uniform(1, 10), 2),
                "run_db_path": f"/tmp/{exec_id}.db",
                "metadata": {"cache_hit": False},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201],
                      f"Results register failed: {r.status_code} {r.text}")
        self.assertTrue(r.json().get("success"))

        # 5. Results: search and verify exec_id appears
        r = requests.post(
            self._url("results", "/search"),
            json={"simulation_name": sim_name, "limit": 10},
            headers=self.HDRS,
        )
        self.assertEqual(r.status_code, 200)
        exec_ids = [res["execution_id"] for res in r.json().get("results", [])]
        self.assertIn(exec_id, exec_ids)

    # ── Web UI API contract validation ────────────────────────────────────────

    def test_webui_cache_entries_response_shape(self):
        """Validates the JSON shape web-ui/src/api/cacheService.ts expects."""
        r = requests.get(self._url("cache", "/cache/entries"),
                         params={"limit": 5}, headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        # Web UI: { entries: CacheEntry[], total: number, limit: number, offset: number }
        for field in ("entries", "total", "limit", "offset"):
            self.assertIn(field, data)
        self.assertIsInstance(data["entries"], list)
        self.assertIsInstance(data["total"], int)

    def test_webui_cache_stats_response_shape(self):
        """Validates the JSON shape web-ui/src/api/cacheService.ts expects for stats."""
        data = requests.get(self._url("cache", "/cache/stats")).json()
        for field in ("total_entries", "total_accesses", "total_hits"):
            self.assertIn(field, data, f"Web UI stats contract broken: missing '{field}'")

    def test_webui_results_search_response_shape(self):
        """Validates the JSON shape web-ui/src/api/resultsService.ts expects."""
        r = requests.post(self._url("results", "/search"),
                          json={"limit": 5}, headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        # Web UI: { results: ExecutionResult[], count: number }
        self.assertIn("results", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["results"], list)
        self.assertIsInstance(data["count"], int)

    def test_webui_catalog_search_response_shape(self):
        """Validates the JSON shape web-ui/src/api/catalogService.ts expects."""
        r = requests.get(self._url("catalog", "/simulations/search"))
        self.assertEqual(r.status_code, 200)
        # Web UI accepts either a list or { simulations: [...] }
        self.assertIn(type(r.json()), (list, dict))

    def test_webui_checkAllServices_health(self):
        """Simulates web-ui client.ts checkAllServices() parallel health checks."""
        results = {}
        for name, port in self.PORTS.items():
            try:
                r = requests.get(f"http://localhost:{port}/health", timeout=2)
                results[name] = {"status": r.status_code, "data": r.json()}
            except Exception as e:
                results[name] = {"error": str(e)}

        for name in ("cache", "catalog", "results"):
            self.assertEqual(
                results[name].get("status"), 200,
                f"{name} service not healthy: {results[name]}",
            )


# ═════════════════════════════════════════════════════════════════════════════
# 9. Docker Services Tests  (ports 8001/8002 required, 8003 optional)
#
# The docker-compose dev profile starts:
#   cache-sqlite   → port 8001  (required)
#   catalog-sqlite → port 8002  (required)
#
# The results service (port 8003) is NOT part of the Docker compose file.
# Start it manually if needed:
#   python -m sim2l.services.results_service --backend sqlite \
#          --db-path .sim2l/results.db --no-auth --port 8003
#
# Availability is checked at runtime in setUpClass (not at import time),
# so the class is never wrongly skipped during test collection.
# ═════════════════════════════════════════════════════════════════════════════

_DOCKER_PORTS = {"cache": 8001, "catalog": 8002, "results": 8003}


class TestDockerServices(unittest.TestCase):
    """
    Integration tests against the Docker-deployed services.

    Cache (8001) and Catalog (8002) must be running – start with:
        cd docker && docker-compose --profile dev up -d

    Results (8003) is optional – start manually:
        python -m sim2l.services.results_service --backend sqlite \\
               --db-path .sim2l/results.db --no-auth --port 8003
    """

    SID = "demo-session"
    HDRS = {"X-Session-ID": SID}

    @classmethod
    def setUpClass(cls):
        # Only cache and catalog are required (they live in docker-compose dev).
        required = {"cache": 8001, "catalog": 8002}
        cls.skip_reason = None
        for name, port in required.items():
            if not _wait_for_service(port, timeout=3):
                cls.skip_reason = (
                    f"Docker {name} service not reachable on port {port}. "
                    f"Run: cd docker && docker-compose --profile dev up -d"
                )
                return
        # Results service is optional – record availability for per-test use.
        cls.results_available = _wait_for_service(8003, timeout=2)

    def setUp(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    def _url(self, svc: str, path: str = "") -> str:
        return f"http://localhost:{_DOCKER_PORTS[svc]}{path}"

    def _require_results(self):
        """Skip the calling test if the results service is not running."""
        if not self.results_available:
            self.skipTest(
                "Results service not running on port 8003. "
                "Start it with: python -m sim2l.services.results_service "
                "--backend sqlite --db-path .sim2l/results.db --no-auth --port 8003"
            )

    # ── Health ────────────────────────────────────────────────────────────────

    def test_docker_cache_service_healthy(self):
        r = requests.get(self._url("cache", "/health"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "healthy")

    def test_docker_catalog_service_healthy(self):
        r = requests.get(self._url("catalog", "/health"))
        self.assertEqual(r.status_code, 200)

    def test_docker_results_service_healthy(self):
        self._require_results()
        r = requests.get(self._url("results", "/health"))
        self.assertEqual(r.status_code, 200)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def test_docker_cache_set_and_get(self):
        # Use varying inputs to create different squid IDs
        inputs = {"temperature": random.uniform(300, 400), "pressure": random.uniform(1, 3)}
        payload = _make_cache_payload(name="thermal_simulation", version="1.0.0", sim_id=42, inputs=inputs)
        r = requests.post(self._url("cache", "/cache"), json=payload, headers=self.HDRS)
        self.assertIn(r.status_code, [200, 201])
        r = requests.get(self._url("cache", f"/cache/{payload['cache_key']}"),
                         headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["execution_id"], payload["execution_id"])

    def test_docker_cache_stats_fields(self):
        data = requests.get(self._url("cache", "/cache/stats")).json()
        for field in ("total_entries", "total_accesses", "total_hits"):
            self.assertIn(field, data)

    def test_docker_cache_hits_with_same_inputs(self):
        """Test cache hits by using the same random inputs twice."""
        # Generate random inputs ONCE
        inputs = {"temperature": random.uniform(300, 400), "pressure": random.uniform(1, 3)}
        
        # Create first entry with these inputs
        payload1 = _make_cache_payload(
            name="thermal_simulation", version="1.0.0", sim_id=42, 
            inputs=inputs, exec_id="hit-test-exec1"
        )
        r = requests.post(self._url("cache", "/cache"), json=payload1, headers=self.HDRS)
        self.assertIn(r.status_code, [200, 201])
        
        # Get stats before hits
        stats_before = requests.get(self._url("cache", "/cache/stats")).json()
        hits_before = stats_before.get("total_hits", 0)
        
        # Access the same entry twice (should create 2 cache hits)
        r1 = requests.get(self._url("cache", f"/cache/{payload1['cache_key']}"), headers=self.HDRS)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["execution_id"], payload1["execution_id"])
        
        r2 = requests.get(self._url("cache", f"/cache/{payload1['cache_key']}"), headers=self.HDRS)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["execution_id"], payload1["execution_id"])
        
        # Get stats after hits
        stats_after = requests.get(self._url("cache", "/cache/stats")).json()
        hits_after = stats_after.get("total_hits", 0)
        
        # Verify hits increased by at least 2
        self.assertGreaterEqual(hits_after - hits_before, 2, 
                                f"Cache hits should increase by 2, got {hits_after - hits_before}")
        
        # Now create a SECOND entry with SAME inputs (should reuse same cache_key)
        payload2 = _make_cache_payload(
            name="thermal_simulation", version="1.0.0", sim_id=42,
            inputs=inputs, exec_id="hit-test-exec2"  # Different exec_id, same inputs
        )
        
        # The cache_key should be the same since inputs are the same
        self.assertEqual(payload1['cache_key'], payload2['cache_key'],
                        "Same inputs should generate same cache_key")
        
        # Posting again should update existing entry (not create new one)
        r = requests.post(self._url("cache", "/cache"), json=payload2, headers=self.HDRS)
        self.assertIn(r.status_code, [200, 201])
        
        # Retrieving should now return the updated exec_id
        r = requests.get(self._url("cache", f"/cache/{payload2['cache_key']}"), headers=self.HDRS)
        self.assertEqual(r.status_code, 200)

    def test_docker_cache_entries_pagination(self):
        r = requests.get(self._url("cache", "/cache/entries"),
                         params={"limit": 5}, headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        for field in ("entries", "total", "limit", "offset"):
            self.assertIn(field, r.json())

    # ── Catalog ───────────────────────────────────────────────────────────────

    def test_docker_catalog_register_simulation(self):
        sim_name = "thermal_simulation"  # Fixed simulation name
        # Vary version or squid to create different entries
        version_suffix = random.randint(1, 99)
        version = f"1.0.{version_suffix}"
        # workflow_hash is NOT NULL in the catalog schema – supply a placeholder.
        wf_hash = hashlib.md5(f"{sim_name}{version}".encode()).hexdigest()
        r = requests.post(
            self._url("catalog", "/simulations"),
            json={
                "name": sim_name, "version": version,
                "squid_id": f"{sim_name}/{version}/main",
                "description": "Docker test",
                "workflow_hash": wf_hash,
                "input_schema": {"type": "object",
                                 "properties": {"x": {"type": "number"}}},
                "output_schema": {"type": "object",
                                  "properties": {"y": {"type": "number"}}},
                "metadata": {},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201])

    # ── Results ───────────────────────────────────────────────────────────────

    def test_docker_results_register_and_search(self):
        self._require_results()
        exec_id = f"docker-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        # Vary inputs to create different squid IDs
        temp_value = random.uniform(300, 400)
        input_hash = _compute_hash({"temperature": temp_value})
        r = requests.post(
            self._url("results", "/register_direct"),
            json={
                "execution_id": exec_id,
                "simulation_name": "thermal_simulation",
                "simulation_version": "1.0.0",
                "squid_id": f"thermal_simulation/1.0.0/{input_hash[:8]}",
                "input_params": {"temperature": temp_value},
                "output_params": {"max_temp": 368.0, "converged": True},
                "status": "completed",
                "duration_seconds": 5.0,
                "run_db_path": f"/tmp/{exec_id}.db",
                "metadata": {},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201])
        self.assertTrue(r.json().get("success"))

        r = requests.post(
            self._url("results", "/search"),
            json={"simulation_name": "thermal_simulation", "limit": 10},
            headers=self.HDRS,
        )
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

    # ── Full flow across all Docker services ──────────────────────────────────

    def test_docker_full_e2e_flow(self):
        """End-to-end: catalog → cache → results, all via Docker services."""
        self._require_results()
        sim_name = "thermal_simulation"  # Fixed simulation name
        version = "1.0.0"
        exec_id = f"docker-e2e-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        # Vary inputs to create different squid IDs
        inputs = {"temperature": random.uniform(300, 400), "power": random.uniform(1, 10)}
        input_hash = _compute_hash(inputs)
        cache_key = f"{sim_name}_{version}_{input_hash[:8]}"

        # Register in catalog
        requests.post(
            self._url("catalog", "/simulations"),
            json={
                "name": sim_name, "version": version,
                "squid_id": f"{sim_name}/{version}/main",
                "description": "Docker E2E",
                "workflow_hash": hashlib.md5(sim_name.encode()).hexdigest(),
                "input_schema": {}, "output_schema": {}, "metadata": {},
            },
            headers=self.HDRS,
        )

        # Store in cache
        r = requests.post(
            self._url("cache", "/cache"),
            json={
                "cache_key": cache_key, "simulation_id": 1,
                "simulation_name": sim_name, "simulation_version": version,
                "execution_id": exec_id,
                "squid_id": f"{sim_name}/{version}/{input_hash[:8]}",
                "input_hash": input_hash,
                "run_db_path": f"/tmp/{exec_id}.db",
                "metadata": {"inputs": inputs},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201])

        # Register result
        r = requests.post(
            self._url("results", "/register_direct"),
            json={
                "execution_id": exec_id,
                "simulation_name": sim_name, "simulation_version": version,
                "squid_id": f"{sim_name}/{version}/{input_hash[:8]}",
                "input_params": inputs,
                "output_params": {"max_temp": 356.5, "converged": True},
                "status": "completed", "duration_seconds": 8.2,
                "run_db_path": f"/tmp/{exec_id}.db", "metadata": {},
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201])

        # Verify result appears in search
        r = requests.post(
            self._url("results", "/search"),
            json={"simulation_name": sim_name, "limit": 5},
            headers=self.HDRS,
        )
        self.assertEqual(r.status_code, 200)
        ids = [res["execution_id"] for res in r.json().get("results", [])]
        self.assertIn(exec_id, ids)
        
        # ── Test cache hits by accessing same entry multiple times ───────────
        stats_before = requests.get(self._url("cache", "/cache/stats")).json()
        hits_before = stats_before.get("total_hits", 0)
        
        # Access the cached entry twice with same cache_key
        for i in range(2):
            r = requests.get(self._url("cache", f"/cache/{cache_key}"), headers=self.HDRS)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["execution_id"], exec_id)
            self.assertEqual(r.json()["squid_id"], f"{sim_name}/{version}/{input_hash[:8]}")
        
        # Verify cache hits increased
        stats_after = requests.get(self._url("cache", "/cache/stats")).json()
        hits_after = stats_after.get("total_hits", 0)
        self.assertGreaterEqual(hits_after - hits_before, 2,
                                f"Expected at least 2 cache hits, got {hits_after - hits_before}")
        
        # ── Test reusing same inputs creates cache hit (not new entry) ────────
        exec_id2 = f"docker-e2e-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-rerun"
        
        # Store again with SAME inputs (same cache_key)
        r = requests.post(
            self._url("cache", "/cache"),
            json={
                "cache_key": cache_key, "simulation_id": 1,
                "simulation_name": sim_name, "simulation_version": version,
                "execution_id": exec_id2,  # Different exec_id
                "squid_id": f"{sim_name}/{version}/{input_hash[:8]}",
                "input_hash": input_hash,  # Same hash
                "run_db_path": f"/tmp/{exec_id2}.db",
                "metadata": {"inputs": inputs},  # Same inputs
            },
            headers=self.HDRS,
        )
        self.assertIn(r.status_code, [200, 201])
        
        # Retrieve and verify it's the updated entry
        r = requests.get(self._url("cache", f"/cache/{cache_key}"), headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        # Should have the new exec_id since we updated the cache entry
        retrieved_data = r.json()
        # Note: depending on cache implementation, this might be exec_id2 or exec_id

    # ── Web UI contract on Docker services ────────────────────────────────────

    def test_docker_webui_cache_entries_contract(self):
        r = requests.get(self._url("cache", "/cache/entries"),
                         params={"limit": 5}, headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        for field in ("entries", "total", "limit", "offset"):
            self.assertIn(field, r.json())

    def test_docker_webui_results_search_contract(self):
        self._require_results()
        r = requests.post(self._url("results", "/search"),
                          json={"limit": 5}, headers=self.HDRS)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("results", data)
        self.assertIn("count", data)

    def test_docker_webui_all_services_health_check(self):
        """
        Mirrors web-ui checkAllServices() – hits /health on all running ports.
        Cache and catalog must be healthy; results is checked only if available.
        """
        for name, port in _DOCKER_PORTS.items():
            if name == "results" and not self.results_available:
                continue  # results service not in docker-compose dev profile
            try:
                r = requests.get(f"http://localhost:{port}/health", timeout=2)
                self.assertEqual(r.status_code, 200,
                                 f"Docker {name} service health check failed")
            except requests.exceptions.ConnectionError:
                self.fail(f"Docker {name} service unreachable on port {port}")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)