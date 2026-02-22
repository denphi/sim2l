# Test Layout

This repository keeps executable tests under test-focused directories.

## Automated tests (pytest/unittest)

- `tests/`: top-level integration and workflow tests.
- `tests/system/`: service health and system-level checks.
- `tests/web_ui/`: backend API behavior used by the web UI.
- `sim2l/tests/`: package-level unit and integration tests for `sim2l`.

Run:

```bash
python3 -m pytest -vv
```

Pytest now auto-bootstraps local cache/catalog/results services on ports
`8001`, `8002`, and `8003` for service-dependent tests.

To disable bootstrap in a custom environment:

```bash
SIM2L_TEST_BOOTSTRAP_SERVICES=0 python3 -m pytest -vv
```

Use `-s` to show explanatory print output:

```bash
python3 -m pytest -vv -s
```

PostgreSQL-dependent tests need a running local PostgreSQL instance. Start it with Docker:

```bash
./start_postgres_services.sh
```

Schema details and initialization ownership are documented in:

```bash
sim2l/database/SCHEMAS.md
```

If a local PostgreSQL is already running on `localhost:5432`, the script will reuse it
and still create the required test databases.

Run PostgreSQL integration tests:

```bash
python3 -m pytest -vv sim2l/tests/test_postgres_catalog_integration.py
python3 -m pytest -vv tests/test_catalog_postgres_backend_integration.py
```

Stop Docker PostgreSQL:

```bash
./stop_postgres_services.sh
```

## Manual demos

`tests/manual/` contains interactive/demo scripts that explain scenarios and are run manually.
They are intentionally not auto-collected by pytest.

Run any demo directly, for example:

```bash
python3 tests/manual/cache_service_direct_demo.py
python3 tests/manual/ui_interactive_check.py
```
