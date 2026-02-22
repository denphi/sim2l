#!/bin/bash
# Start PostgreSQL for sim2l integration tests.
# Prefer an existing localhost PostgreSQL (dev or docker). Fall back to docker compose.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "Error: neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
fi

detect_existing_base() {
    python3 - <<'PY'
import psycopg2

candidates = [
    "postgresql://sim2l:sim2l_password@localhost:5432",
]

for base in candidates:
    try:
        conn = psycopg2.connect(f"{base}/postgres", connect_timeout=2)
        conn.close()
        print(base)
        raise SystemExit(0)
    except Exception:
        continue

raise SystemExit(1)
PY
}

ensure_databases_host() {
    local base_url="$1"
    python3 - "$base_url" <<'PY'
import sys
import psycopg2
from psycopg2 import sql

base_url = sys.argv[1]
conn = psycopg2.connect(f"{base_url}/postgres", connect_timeout=3)
conn.autocommit = True
cur = conn.cursor()

for db_name in ("sim2l_cache", "sim2l_catalog", "sim2l_results", "sim2l_test"):
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    if cur.fetchone() is None:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO sim2l").format(sql.Identifier(db_name)))

cur.execute("ALTER USER sim2l WITH PASSWORD %s", ("sim2l_password",))

cur.close()
conn.close()
PY
}

ensure_databases_container() {
    local container_id="$1"
    docker exec -i "$container_id" psql -U sim2l -d postgres -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'CREATE DATABASE sim2l_cache'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sim2l_cache')\gexec
SELECT 'CREATE DATABASE sim2l_catalog'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sim2l_catalog')\gexec
SELECT 'CREATE DATABASE sim2l_results'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sim2l_results')\gexec
SELECT 'CREATE DATABASE sim2l_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sim2l_test')\gexec

GRANT ALL PRIVILEGES ON DATABASE sim2l_cache TO sim2l;
GRANT ALL PRIVILEGES ON DATABASE sim2l_catalog TO sim2l;
GRANT ALL PRIVILEGES ON DATABASE sim2l_results TO sim2l;
GRANT ALL PRIVILEGES ON DATABASE sim2l_test TO sim2l;
ALTER USER sim2l WITH PASSWORD 'sim2l_password';
SQL
}

if EXISTING_BASE="$(detect_existing_base 2>/dev/null)"; then
    echo "Using existing PostgreSQL at ${EXISTING_BASE} (docker start skipped)."
    ensure_databases_host "$EXISTING_BASE"
    TEST_DB_URL="${EXISTING_BASE}/sim2l_test"
else
    # If some other docker container already publishes 5432, normalize that one first.
    EXISTING_CONTAINER_ON_5432="$(docker ps --filter publish=5432 --format '{{.ID}}' | head -n 1 || true)"
    if [[ -n "$EXISTING_CONTAINER_ON_5432" ]]; then
        echo "Port 5432 is already published by container ${EXISTING_CONTAINER_ON_5432}."
        echo "Attempting credential/database normalization on that container ..."
        if ! ensure_databases_container "$EXISTING_CONTAINER_ON_5432"; then
            echo "Error: container ${EXISTING_CONTAINER_ON_5432} is not usable as sim2l PostgreSQL." >&2
            exit 1
        fi
        if EXISTING_BASE="$(detect_existing_base 2>/dev/null)"; then
            TEST_DB_URL="${EXISTING_BASE}/sim2l_test"
        else
            echo "Error: PostgreSQL is on port 5432 but sim2l_password authentication still failed." >&2
            exit 1
        fi
    else
        echo "Starting PostgreSQL container from $COMPOSE_FILE ..."
        if ! "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" --profile prod up -d postgres; then
            echo "Error: failed to start docker PostgreSQL." >&2
            echo "If port 5432 is already used by a different PostgreSQL instance," >&2
            echo "stop that instance (or reconfigure it to use sim2l_password) and retry." >&2
            exit 1
        fi

        PG_CONTAINER="$("${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" ps -q postgres)"
        if [[ -z "$PG_CONTAINER" ]]; then
            echo "Error: postgres container was not created." >&2
            exit 1
        fi

        echo "Waiting for PostgreSQL health check ..."
        for _ in $(seq 1 60); do
            HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$PG_CONTAINER" 2>/dev/null || true)"
            if [[ "$HEALTH" == "healthy" || "$HEALTH" == "running" ]]; then
                break
            fi
            sleep 1
        done

        HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$PG_CONTAINER" 2>/dev/null || true)"
        if [[ "$HEALTH" != "healthy" && "$HEALTH" != "running" ]]; then
            echo "Error: PostgreSQL did not become healthy (state: $HEALTH)." >&2
            echo "Check logs with: ${COMPOSE_CMD[*]} -f \"$COMPOSE_FILE\" logs postgres" >&2
            exit 1
        fi

        echo "Ensuring test databases exist ..."
        ensure_databases_container "$PG_CONTAINER"
        TEST_DB_URL="postgresql://sim2l:sim2l_password@localhost:5432/sim2l_test"
    fi
fi

echo
echo "PostgreSQL is ready for integration tests."
echo "POSTGRES_URL=${TEST_DB_URL}"
echo
echo "Run:"
echo "  python3 -m pytest -q sim2l/tests/test_postgres_catalog_integration.py"
echo "  python3 -m pytest -q tests/test_catalog_postgres_backend_integration.py"
