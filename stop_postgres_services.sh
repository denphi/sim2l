#!/bin/bash
# Stop Docker PostgreSQL services used by sim2l tests.

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

echo "Stopping PostgreSQL container from $COMPOSE_FILE ..."
"${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" --profile prod down
