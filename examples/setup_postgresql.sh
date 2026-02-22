#!/bin/bash
# PostgreSQL Setup Script for sim2l
# This script creates the necessary PostgreSQL databases for sim2l services

set -e

# Configuration
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

# Database names
CACHE_DB="sim2l_cache"
CATALOG_DB="sim2l_catalog"
RESULTS_DB="sim2l_results"

echo "========================================================================"
echo "sim2l PostgreSQL Setup"
echo "========================================================================"
echo ""
echo "This script will create three PostgreSQL databases:"
echo "  1. $CACHE_DB    - Cache service database"
echo "  2. $CATALOG_DB  - Catalog service database"
echo "  3. $RESULTS_DB  - Results service database"
echo ""
echo "PostgreSQL connection:"
echo "  Host: $POSTGRES_HOST"
echo "  Port: $POSTGRES_PORT"
echo "  User: $POSTGRES_USER"
echo ""

# Function to execute psql command
psql_exec() {
    if [ -n "$POSTGRES_PASSWORD" ]; then
        PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$@"
    else
        psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$@"
    fi
}

# Check if PostgreSQL is running
echo "Checking PostgreSQL connection..."
if ! psql_exec -c "SELECT version();" postgres > /dev/null 2>&1; then
    echo "✗ Failed to connect to PostgreSQL"
    echo ""
    echo "Please ensure PostgreSQL is running and the connection parameters are correct."
    echo "You can set environment variables:"
    echo "  export POSTGRES_HOST=localhost"
    echo "  export POSTGRES_PORT=5432"
    echo "  export POSTGRES_USER=postgres"
    echo "  export POSTGRES_PASSWORD=yourpassword"
    exit 1
fi
echo "✓ PostgreSQL connection successful"
echo ""

# Create databases
echo "Creating databases..."

for db in "$CACHE_DB" "$CATALOG_DB" "$RESULTS_DB"; do
    echo "  Creating $db..."
    if psql_exec -lqt postgres | cut -d \| -f 1 | grep -qw "$db"; then
        echo "    ⚠ Database $db already exists, dropping and recreating..."
        psql_exec -c "DROP DATABASE IF EXISTS $db;" postgres
    fi
    psql_exec -c "CREATE DATABASE $db;" postgres
    echo "    ✓ Database $db created"
done

echo ""
echo "✓ All databases created successfully!"
echo ""

# Get the schema directory
SCHEMA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../sim2l/database" && pwd)"

echo "Initializing schemas..."

# Initialize cache database
echo "  Initializing $CACHE_DB..."
psql_exec -d "$CACHE_DB" -f "$SCHEMA_DIR/cache_service_schema.sql" > /dev/null
echo "    ✓ Cache schema initialized"

# Initialize catalog database
echo "  Initializing $CATALOG_DB..."
psql_exec -d "$CATALOG_DB" -f "$SCHEMA_DIR/master_catalog_schema.sql" > /dev/null
echo "    ✓ Catalog schema initialized"

# Initialize results database
echo "  Initializing $RESULTS_DB..."
psql_exec -d "$RESULTS_DB" -f "$SCHEMA_DIR/results_db_schema.sql" > /dev/null
echo "    ✓ Results schema initialized"

echo ""
echo "========================================================================"
echo "Setup Complete!"
echo "========================================================================"
echo ""
echo "Connection strings for services:"
echo ""
echo "Cache Service:"
echo "  postgresql://$POSTGRES_USER@$POSTGRES_HOST:$POSTGRES_PORT/$CACHE_DB"
echo ""
echo "Catalog Service:"
echo "  postgresql://$POSTGRES_USER@$POSTGRES_HOST:$POSTGRES_PORT/$CATALOG_DB"
echo ""
echo "Results Service:"
echo "  postgresql://$POSTGRES_USER@$POSTGRES_HOST:$POSTGRES_PORT/$RESULTS_DB"
echo ""
echo "To start services with PostgreSQL:"
echo "  python3 -m sim2l.services.cache_service --backend postgresql --db-url 'postgresql://$POSTGRES_USER@$POSTGRES_HOST:$POSTGRES_PORT/$CACHE_DB' --no-auth"
echo "  python3 -m sim2l.services.catalog_service --backend postgresql --db-url 'postgresql://$POSTGRES_USER@$POSTGRES_HOST:$POSTGRES_PORT/$CATALOG_DB'"
echo "  python3 -m sim2l.services.results_service --backend postgresql --db-url 'postgresql://$POSTGRES_USER@$POSTGRES_HOST:$POSTGRES_PORT/$RESULTS_DB' --no-auth"
echo ""
