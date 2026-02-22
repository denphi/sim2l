# sim2l Schema Overview

This document describes the authoritative database schemas used by `sim2l`,
how they are initialized, and how to validate them.

## Schema files

### `cache_service_schema.sql`
- Database: `sim2l_cache` (PostgreSQL) or adapted at runtime for SQLite.
- Used by: `sim2l.services.cache_service`.
- Main objects:
  - `cache_entries`, `cache_sessions`, `cache_access_log`
  - cache views/functions such as `get_cache_entry`, `set_cache_entry`

### `master_catalog_schema.sql`
- Database: `sim2l_catalog` (PostgreSQL) or adapted at runtime for SQLite.
- Used by: `sim2l.services.catalog_service`.
- Main objects:
  - `simulations`, `sessions`, `users`, `execution_registry`
  - views (`simulation_catalog`, etc.)
  - triggers for `updated_at`

### `results_db_schema.sql`
- Database: `sim2l_results` (PostgreSQL).
- Used by: `sim2l.services.results_service` PostgreSQL backend.
- Main objects:
  - `simulation_schemas`, `execution_results`, `parameter_definitions`
  - search functions (`search_results_by_params`, `matches_jsonb_filter`)

### `run_db_schema.sql`
- Database: per-execution local SQLite file.
- Used by: `sim2l.database.run_database.RunDatabase`.
- Main objects:
  - `run_metadata`, `inputs`, `outputs`, `artifacts`, `logs`

## Initialization flow

### Docker production stack (`docker/docker-compose.yml`)
- `docker/init-db.sql` creates:
  - `sim2l_cache`
  - `sim2l_catalog`
  - `sim2l_results`
  - `sim2l_test`

### Example stack (`examples/docker-compose.yml`)
- `examples/init_postgres.sh` creates the same databases and initializes
  cache/catalog/results schemas.
- `sim2l_test` is created for integration tests; tests manage its objects.

### Test bootstrap script
- `./start_postgres_services.sh`:
  - starts or reuses PostgreSQL on `localhost:5432`
  - enforces `sim2l_password` for user `sim2l`
  - ensures required databases exist

## Idempotency notes

- Cache schema is designed to be reapplied safely (`IF NOT EXISTS`,
  `CREATE OR REPLACE FUNCTION`).
- Catalog schema includes trigger creation that is not fully idempotent; therefore
  `PostgreSQLCatalogBackend` only applies full schema at first initialization and
  then performs targeted non-breaking upgrades.
- Results PostgreSQL backend expects schema to already exist (initialized by Docker
  or setup scripts). Integration tests explicitly initialize/drop result objects.
- Run DB schema is created per-run in a fresh SQLite file.

## Validation commands

Start PostgreSQL and ensure databases:

```bash
./start_postgres_services.sh
```

Validate PostgreSQL-backed schemas via tests:

```bash
python3 -m pytest -q sim2l/tests/test_postgres_catalog_integration.py
python3 -m pytest -q tests/test_catalog_postgres_backend_integration.py
```

Validate local SQLite run DB schema:

```bash
python3 -m pytest -q sim2l/tests/database/test_run_database.py
```
