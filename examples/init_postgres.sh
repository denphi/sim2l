#!/bin/bash
# PostgreSQL initialization script for Docker container
# This script runs automatically when the container starts for the first time

set -e

echo "Initializing sim2l PostgreSQL databases..."

# Create databases
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE sim2l_cache;
    CREATE DATABASE sim2l_catalog;
    CREATE DATABASE sim2l_results;
EOSQL

echo "✓ Databases created"

# Initialize schemas
echo "Initializing cache schema..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "sim2l_cache" < /schemas/cache_service_schema.sql

echo "Initializing catalog schema..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "sim2l_catalog" < /schemas/master_catalog_schema.sql

echo "Initializing results schema..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "sim2l_results" < /schemas/results_db_schema.sql

echo "✓ All schemas initialized successfully!"
