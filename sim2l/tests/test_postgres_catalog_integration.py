"""
PostgreSQL integration tests for sim2l services.

Requires a running PostgreSQL instance. Tests are automatically skipped
with a warning if PostgreSQL is not reachable.

Set the POSTGRES_URL environment variable to override the default:
    export POSTGRES_URL="postgresql://sim2l:sim2l_password@localhost:5432/sim2l_test"

Default connection uses the docker-compose credentials:
    postgresql://sim2l:sim2l_password@localhost:5432/sim2l_test
"""

import os
import json
import uuid
import pytest

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _check_postgres(url: str) -> bool:
    """Return True if a PostgreSQL connection can be established."""
    try:
        import psycopg2
        conn = psycopg2.connect(url, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def _candidate_postgres_bases() -> list[str]:
    """Return PostgreSQL base URLs to try, in priority order."""
    candidates = []

    env_url = os.environ.get("POSTGRES_URL")
    if env_url:
        candidates.append(env_url.rsplit("/", 1)[0])

    candidates.extend(
        [
            "postgresql://sim2l:sim2l_password@localhost:5432",
        ]
    )

    # Preserve order while removing duplicates.
    seen = set()
    unique = []
    for base in candidates:
        if base not in seen:
            unique.append(base)
            seen.add(base)
    return unique


def _detect_postgres_test_url() -> str | None:
    """
    Detect a reachable PostgreSQL base and ensure `sim2l_test` exists.

    Returns:
        Full URL to `sim2l_test` if reachable, else None.
    """
    try:
        import psycopg2
        from psycopg2 import sql
    except Exception:
        return None

    for base in _candidate_postgres_bases():
        try:
            admin = psycopg2.connect(f"{base}/postgres", connect_timeout=3)
            admin.autocommit = True
            cur = admin.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("sim2l_test",))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("sim2l_test")))
            cur.close()
            admin.close()

            test_url = f"{base}/sim2l_test"
            if _check_postgres(test_url):
                return test_url
        except Exception:
            continue

    return None


# Module-level skip if PostgreSQL is not available
_detected_postgres_url = _detect_postgres_test_url()
postgres_url = _detected_postgres_url or (
    _candidate_postgres_bases()[0] + "/sim2l_test"
)
postgres_available = _detected_postgres_url is not None

pytestmark = pytest.mark.skipif(
    not postgres_available,
    reason=(
        f"PostgreSQL not reachable at {postgres_url} — "
        "start it with ./start_postgres_services.sh"
    ),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_url():
    """Provide the PostgreSQL URL for this test session."""
    return postgres_url


@pytest.fixture(scope="function")
def pg_conn(pg_url):
    """Raw psycopg2 connection for setup/teardown."""
    import psycopg2
    conn = psycopg2.connect(pg_url)
    conn.autocommit = True
    yield conn
    conn.close()


def _drop_results_schema(cursor):
    cursor.execute("DROP TABLE IF EXISTS result_search_cache CASCADE")
    cursor.execute("DROP TABLE IF EXISTS result_errors CASCADE")
    cursor.execute("DROP TABLE IF EXISTS parameter_definitions CASCADE")
    cursor.execute("DROP TABLE IF EXISTS execution_results CASCADE")
    cursor.execute("DROP TABLE IF EXISTS simulation_schemas CASCADE")
    cursor.execute("DROP FUNCTION IF EXISTS register_simulation_schema CASCADE")
    cursor.execute("DROP FUNCTION IF EXISTS register_execution_result CASCADE")
    cursor.execute("DROP FUNCTION IF EXISTS search_results_by_params CASCADE")
    cursor.execute("DROP FUNCTION IF EXISTS matches_jsonb_filter CASCADE")
    cursor.execute("DROP FUNCTION IF EXISTS get_parameter_statistics CASCADE")
    cursor.execute("DROP FUNCTION IF EXISTS update_schema_timestamp CASCADE")
    cursor.execute("DROP VIEW IF EXISTS full_execution_results CASCADE")


@pytest.fixture(scope="function")
def clean_results_schema(pg_conn):
    """Drop and recreate the results schema tables before each test."""
    from pathlib import Path
    schema_path = Path(__file__).parent.parent / "database" / "results_db_schema.sql"

    cursor = pg_conn.cursor()
    _drop_results_schema(cursor)

    with open(schema_path) as f:
        cursor.execute(f.read())

    yield

    _drop_results_schema(cursor)


@pytest.fixture(scope="function")
def clean_cache_schema(pg_conn):
    """Drop and recreate the cache schema tables before each test."""
    from pathlib import Path
    schema_path = Path(__file__).parent.parent / "database" / "cache_service_schema.sql"

    cursor = pg_conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cache_entries CASCADE")
    cursor.execute("DROP TABLE IF EXISTS cache_sessions CASCADE")

    with open(schema_path) as f:
        cursor.execute(f.read())

    yield

    cursor.execute("DROP TABLE IF EXISTS cache_entries CASCADE")
    cursor.execute("DROP TABLE IF EXISTS cache_sessions CASCADE")


@pytest.fixture(scope="function")
def results_backend(pg_url, clean_results_schema):
    """Provide a ready-to-use PostgreSQLResultsBackend."""
    from sim2l.services.results_service import PostgreSQLResultsBackend
    backend = PostgreSQLResultsBackend(pg_url)
    yield backend
    # Close connection so teardown DROP statements don't block
    conn = getattr(backend._local, "conn", None)
    if conn and not conn.closed:
        conn.close()


@pytest.fixture(scope="function")
def cache_backend(pg_url, clean_cache_schema):
    """Provide a ready-to-use PostgreSQLCacheBackend (no-auth mode)."""
    from sim2l.services.cache_service import PostgreSQLCacheBackend
    backend = PostgreSQLCacheBackend(pg_url, no_auth=True)
    yield backend
    conn = getattr(backend._local, "conn", None)
    if conn and not conn.closed:
        conn.close()


# ---------------------------------------------------------------------------
# PostgreSQL Results Backend tests
# ---------------------------------------------------------------------------

class TestPostgreSQLResultsBackend:
    """Tests for PostgreSQLResultsBackend."""

    def test_register_schema(self, results_backend):
        """Register a simulation schema and verify it gets an ID."""
        schema_data = {
            "inputs": {"temperature": {"type": "Number", "units": "K"}},
            "outputs": {"max_temp": {"type": "Number", "units": "K"}},
        }
        schema_id = results_backend.register_schema("thermal_sim", "1.0.0", schema_data)
        assert isinstance(schema_id, int)
        assert schema_id > 0

    def test_register_schema_idempotent(self, results_backend):
        """Registering the same schema twice returns the same ID."""
        schema_data = {"inputs": {}, "outputs": {}}
        id1 = results_backend.register_schema("sim_a", "1.0.0", schema_data)
        id2 = results_backend.register_schema("sim_a", "1.0.0", schema_data)
        assert id1 == id2

    def test_register_result(self, results_backend):
        """Register an execution result and verify it is stored."""
        execution_id = str(uuid.uuid4())
        result_id = results_backend.register_result(
            execution_id=execution_id,
            simulation_name="thermal_sim",
            simulation_version="1.0.0",
            squid_id="thermal_sim/1.0.0/abc123",
            input_params={"temperature": 300, "power": 10},
            output_params={"max_temp": 325.5, "converged": True},
            status="completed",
            duration_seconds=12.5,
            run_db_path="/runs/exec.db",
        )
        assert isinstance(result_id, int)
        assert result_id > 0

    def test_get_result(self, results_backend):
        """Retrieve a registered result by execution_id."""
        execution_id = str(uuid.uuid4())
        results_backend.register_result(
            execution_id=execution_id,
            simulation_name="thermal_sim",
            simulation_version="1.0.0",
            squid_id="thermal_sim/1.0.0/abc123",
            input_params={"temperature": 300},
            output_params={"max_temp": 310.0},
            status="completed",
            duration_seconds=5.0,
            run_db_path="/runs/exec.db",
        )

        result = results_backend.get_result(execution_id)
        assert result is not None
        assert result["execution_id"] == execution_id
        assert result["simulation_name"] == "thermal_sim"
        assert result["status"] == "completed"

    def test_get_result_missing(self, results_backend):
        """get_result returns None for an unknown execution_id."""
        result = results_backend.get_result("nonexistent-id")
        assert result is None

    def test_search_results_no_filters(self, results_backend):
        """search_results with no filters returns all stored results."""
        for i in range(3):
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name="thermal_sim",
                simulation_version="1.0.0",
                squid_id=f"thermal_sim/1.0.0/run{i}",
                input_params={"temperature": 300 + i * 10},
                output_params={"max_temp": 310.0 + i},
                status="completed",
                duration_seconds=float(i + 1),
                run_db_path=f"/runs/exec{i}.db",
            )

        results = results_backend.search_results(simulation_name="thermal_sim")
        assert len(results) == 3

    def test_search_results_by_simulation(self, results_backend):
        """search_results filters correctly by simulation name."""
        for name in ["sim_a", "sim_b"]:
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name=name,
                simulation_version="1.0.0",
                squid_id=f"{name}/1.0.0/x",
                input_params={"x": 1},
                output_params={"y": 2},
                status="completed",
                duration_seconds=1.0,
                run_db_path="/runs/exec.db",
            )

        results = results_backend.search_results(simulation_name="sim_a")
        assert len(results) == 1
        assert results[0]["simulation_name"] == "sim_a"

    def test_search_results_input_filter_eq(self, results_backend):
        """search_results filters by exact input parameter value."""
        for temp in [300, 350, 400]:
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name="thermal_sim",
                simulation_version="1.0.0",
                squid_id=f"thermal_sim/1.0.0/t{temp}",
                input_params={"temperature": temp},
                output_params={"max_temp": temp + 10},
                status="completed",
                duration_seconds=1.0,
                run_db_path="/runs/exec.db",
            )

        results = results_backend.search_results(
            simulation_name="thermal_sim",
            input_filters={"temperature": 350},
        )
        assert len(results) == 1
        assert results[0]["input_params"]["temperature"] == 350

    def test_search_results_input_filter_gt(self, results_backend):
        """search_results supports $gt operator on input parameters."""
        for temp in [300, 350, 400]:
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name="thermal_sim",
                simulation_version="1.0.0",
                squid_id=f"thermal_sim/1.0.0/t{temp}",
                input_params={"temperature": temp},
                output_params={"max_temp": temp + 10},
                status="completed",
                duration_seconds=1.0,
                run_db_path="/runs/exec.db",
            )

        results = results_backend.search_results(
            simulation_name="thermal_sim",
            input_filters={"temperature": {"$gt": 300}},
        )
        assert len(results) == 2
        temps = {r["input_params"]["temperature"] for r in results}
        assert temps == {350, 400}

    def test_search_results_input_filter_lte(self, results_backend):
        """search_results supports $lte operator on input parameters."""
        for temp in [300, 350, 400]:
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name="thermal_sim",
                simulation_version="1.0.0",
                squid_id=f"thermal_sim/1.0.0/t{temp}",
                input_params={"temperature": temp},
                output_params={"max_temp": temp + 10},
                status="completed",
                duration_seconds=1.0,
                run_db_path="/runs/exec.db",
            )

        results = results_backend.search_results(
            simulation_name="thermal_sim",
            input_filters={"temperature": {"$lte": 350}},
        )
        assert len(results) == 2

    def test_search_results_by_status(self, results_backend):
        """search_results filters by execution status."""
        for status in ["completed", "completed", "failed"]:
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name="thermal_sim",
                simulation_version="1.0.0",
                squid_id="thermal_sim/1.0.0/x",
                input_params={"x": 1},
                output_params={},
                status=status,
                duration_seconds=1.0,
                run_db_path="/runs/exec.db",
            )

        completed = results_backend.search_results(
            simulation_name="thermal_sim", status="completed"
        )
        failed = results_backend.search_results(
            simulation_name="thermal_sim", status="failed"
        )
        assert len(completed) == 2
        assert len(failed) == 1

    def test_search_results_limit(self, results_backend):
        """search_results respects the limit parameter."""
        for i in range(10):
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name="thermal_sim",
                simulation_version="1.0.0",
                squid_id=f"thermal_sim/1.0.0/r{i}",
                input_params={"x": i},
                output_params={"y": i},
                status="completed",
                duration_seconds=1.0,
                run_db_path="/runs/exec.db",
            )

        results = results_backend.search_results(
            simulation_name="thermal_sim", limit=5
        )
        assert len(results) == 5

    def test_register_result_upsert(self, results_backend):
        """Registering the same execution_id twice updates the record."""
        execution_id = str(uuid.uuid4())
        results_backend.register_result(
            execution_id=execution_id,
            simulation_name="thermal_sim",
            simulation_version="1.0.0",
            squid_id="thermal_sim/1.0.0/x",
            input_params={"temperature": 300},
            output_params={},
            status="running",
            duration_seconds=None,
            run_db_path="/runs/exec.db",
        )
        results_backend.register_result(
            execution_id=execution_id,
            simulation_name="thermal_sim",
            simulation_version="1.0.0",
            squid_id="thermal_sim/1.0.0/x",
            input_params={"temperature": 300},
            output_params={"max_temp": 320.0},
            status="completed",
            duration_seconds=5.0,
            run_db_path="/runs/exec.db",
        )

        result = results_backend.get_result(execution_id)
        assert result["status"] == "completed"
        assert result["output_params"]["max_temp"] == 320.0

    def test_get_parameter_stats(self, results_backend):
        """get_parameter_stats returns min/max/avg for a numeric output."""
        for temp in [300, 350, 400]:
            results_backend.register_result(
                execution_id=str(uuid.uuid4()),
                simulation_name="thermal_sim",
                simulation_version="1.0.0",
                squid_id=f"thermal_sim/1.0.0/t{temp}",
                input_params={"temperature": temp},
                output_params={"max_temp": float(temp + 10)},
                status="completed",
                duration_seconds=1.0,
                run_db_path="/runs/exec.db",
            )

        stats = results_backend.get_parameter_stats("thermal_sim", "max_temp", "output")
        assert stats is not None
        assert stats["min_value"] == pytest.approx(310.0)
        assert stats["max_value"] == pytest.approx(410.0)
        assert stats["avg_value"] == pytest.approx(360.0)
        assert stats["count"] == 3


# ---------------------------------------------------------------------------
# PostgreSQL Cache Backend tests
# ---------------------------------------------------------------------------

class TestPostgreSQLCacheBackend:
    """Tests for PostgreSQLCacheBackend.

    The PostgreSQL backend's set(data, session_id) takes the cache_key inside
    the data dict, and get(cache_key, session_id) returns a (result, status)
    tuple where result is None on a miss.
    """

    SESSION = "demo-session"

    def _make_data(self, key, execution_id, ttl_seconds=None):
        data = {
            "cache_key": key,
            "simulation_id": 1,
            "simulation_name": "thermal_sim",
            "simulation_version": "1.0.0",
            "execution_id": execution_id,
            "squid_id": "thermal_sim/1.0.0/abc",
            "input_hash": "hash123",
            "run_db_path": "/runs/exec.db",
        }
        if ttl_seconds is not None:
            data["ttl_seconds"] = ttl_seconds
        return data

    def _set(self, backend, key, execution_id, ttl_seconds=None):
        backend.set(self._make_data(key, execution_id, ttl_seconds), self.SESSION)

    def _get(self, backend, key):
        result, status = backend.get(key, self.SESSION)
        return result if status == 200 else None

    def test_set_and_get(self, cache_backend):
        """Store an entry and retrieve it."""
        self._set(cache_backend, "k1", "exec-1")
        result = self._get(cache_backend, "k1")
        assert result is not None
        assert result["execution_id"] == "exec-1"

    def test_cache_miss(self, cache_backend):
        """get returns None for a key that was never stored."""
        result = self._get(cache_backend, "nonexistent")
        assert result is None

    def test_set_overwrites_existing(self, cache_backend):
        """A second set for the same key replaces the previous entry."""
        self._set(cache_backend, "k1", "exec-1")
        self._set(cache_backend, "k1", "exec-2")
        result = self._get(cache_backend, "k1")
        assert result["execution_id"] == "exec-2"

    def test_ttl_expiry(self, cache_backend):
        """An entry with ttl_seconds=0 is immediately expired."""
        self._set(cache_backend, "k_ttl", "exec-ttl", ttl_seconds=0)
        result = self._get(cache_backend, "k_ttl")
        assert result is None

    def test_no_ttl_does_not_expire(self, cache_backend):
        """An entry with no TTL is returned without expiry."""
        self._set(cache_backend, "k_notl", "exec-notl", ttl_seconds=None)
        result = self._get(cache_backend, "k_notl")
        assert result is not None

    def test_multiple_entries(self, cache_backend):
        """Multiple independent keys coexist correctly."""
        for i in range(5):
            self._set(cache_backend, f"key{i}", f"exec-{i}")

        for i in range(5):
            result = self._get(cache_backend, f"key{i}")
            assert result is not None
            assert result["execution_id"] == f"exec-{i}"
