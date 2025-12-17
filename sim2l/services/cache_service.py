"""
Standalone cache service for distributed caching.

Provides REST API for cache operations with session-based authentication.
Supports both SQLite (default) and PostgreSQL backends.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# Database backend (will be initialized in main)
cache_db = None
require_auth = True  # Set to False with --no-auth flag


class CacheServiceBackend:
    """Abstract backend for cache service."""

    def get(self, cache_key: str, session_id: str):
        raise NotImplementedError

    def set(self, data: dict, session_id: str):
        raise NotImplementedError

    def invalidate(self, filters: dict, session_id: str):
        raise NotImplementedError

    def get_stats(self, simulation_id: Optional[int]):
        raise NotImplementedError

    def health_check(self):
        raise NotImplementedError


class SQLiteCacheBackend(CacheServiceBackend):
    """SQLite backend for cache service."""

    def __init__(self, db_path: str):
        import sqlite3

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        """Create cache database schema."""
        # Read schema from SQL file
        schema_path = (
            Path(__file__).parent.parent / "database" / "cache_service_schema.sql"
        )

        # For SQLite, we need to adapt the PostgreSQL schema
        with open(schema_path, "r") as f:
            schema_sql = f.read()

        # Simple adaptations for SQLite (order matters!)
        # Do BIGSERIAL before BIGINT to avoid double replacement
        schema_sql = schema_sql.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        schema_sql = schema_sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        schema_sql = schema_sql.replace("BIGINT", "INTEGER")
        schema_sql = schema_sql.replace("JSONB", "TEXT")
        schema_sql = schema_sql.replace("BOOLEAN", "INTEGER")
        schema_sql = schema_sql.replace("DEFAULT true", "DEFAULT 1")
        schema_sql = schema_sql.replace("DEFAULT false", "DEFAULT 0")
        # Keep "IF NOT EXISTS" for tables, but we'll add it back after filtering
        schema_sql = schema_sql.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")

        # Remove PostgreSQL-specific functions and views
        lines = schema_sql.split("\n")
        filtered_lines = []
        skip_until_end = False
        paren_depth = 0

        for line in lines:
            stripped = line.strip()

            # Start skipping when we encounter a function or view
            if "CREATE OR REPLACE FUNCTION" in line or "CREATE OR REPLACE VIEW" in line:
                skip_until_end = True
                paren_depth = 0

            if skip_until_end:
                # Track parentheses and $$ delimiters for function bodies
                if "$$" in line:
                    # Toggle function body delimiter
                    if paren_depth == 0:
                        paren_depth = 1
                    else:
                        paren_depth = 0
                        skip_until_end = False
                elif line.endswith(";") and paren_depth == 0:
                    # End of statement
                    skip_until_end = False
                continue

            # Keep all other lines
            if stripped and not skip_until_end:
                filtered_lines.append(line)

        schema_sql = "\n".join(filtered_lines)

        # Add IF NOT EXISTS back to CREATE TABLE statements
        schema_sql = schema_sql.replace("CREATE TABLE cache_", "CREATE TABLE IF NOT EXISTS cache_")

        # Execute schema
        try:
            self.conn.executescript(schema_sql)
            self.conn.commit()
            logger.info("SQLite cache schema created")
        except Exception as e:
            logger.error(f"Failed to create schema: {e}")

    def _check_session(self, session_id: str) -> bool:
        """Check if session is valid."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM cache_sessions
            WHERE session_id = ?
            AND is_valid = 1
            AND expires_at > datetime('now')
            """,
            (session_id,),
        )
        return cursor.fetchone() is not None

    def get(self, cache_key: str, session_id: str):
        if not self._check_session(session_id):
            return None, 401

        cursor = self.conn.cursor()

        # Update statistics
        cursor.execute(
            """
            UPDATE cache_entries
            SET last_accessed = datetime('now'),
                access_count = access_count + 1,
                hit_count = hit_count + 1
            WHERE cache_key = ?
            AND status = 'valid'
            AND (expires_at IS NULL OR expires_at > datetime('now'))
            """,
            (cache_key,),
        )

        # Get entry
        cursor.execute(
            """
            SELECT execution_id, squid_id, run_db_path, metadata
            FROM cache_entries
            WHERE cache_key = ?
            AND status = 'valid'
            AND (expires_at IS NULL OR expires_at > datetime('now'))
            """,
            (cache_key,),
        )

        row = cursor.fetchone()
        self.conn.commit()

        if row:
            import json

            return {
                "execution_id": row["execution_id"],
                "squid_id": row["squid_id"],
                "run_db_path": row["run_db_path"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            }, 200
        else:
            return None, 404

    def set(self, data: dict, session_id: str):
        if not self._check_session(session_id):
            return {"error": "Unauthorized"}, 401

        import json

        cursor = self.conn.cursor()

        expires_at = None
        if data.get("ttl_seconds"):
            expires_at = f"datetime('now', '+{data['ttl_seconds']} seconds')"

        cursor.execute(
            f"""
            INSERT OR REPLACE INTO cache_entries (
                cache_key, simulation_id, simulation_name, simulation_version,
                execution_id, squid_id, input_hash, run_db_path,
                expires_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, {expires_at or 'NULL'}, ?)
            """,
            (
                data["cache_key"],
                data["simulation_id"],
                data["simulation_name"],
                data["simulation_version"],
                data["execution_id"],
                data["squid_id"],
                data["input_hash"],
                data["run_db_path"],
                json.dumps(data.get("metadata")) if data.get("metadata") else None,
            ),
        )

        self.conn.commit()
        return {"success": True}, 200

    def invalidate(self, filters: dict, session_id: str):
        if not self._check_session(session_id):
            return {"error": "Unauthorized"}, 401

        conditions = ["status = 'valid'"]
        params = []

        if filters.get("simulation_id"):
            conditions.append("simulation_id = ?")
            params.append(filters["simulation_id"])

        if filters.get("simulation_name"):
            conditions.append("simulation_name = ?")
            params.append(filters["simulation_name"])

        if filters.get("simulation_version"):
            conditions.append("simulation_version = ?")
            params.append(filters["simulation_version"])

        if filters.get("pattern"):
            conditions.append("cache_key LIKE ?")
            params.append(filters["pattern"])

        where_clause = " AND ".join(conditions)

        cursor = self.conn.cursor()
        cursor.execute(
            f"""
            UPDATE cache_entries
            SET status = 'invalidated'
            WHERE {where_clause}
            """,
            params,
        )

        invalidated_count = cursor.rowcount
        self.conn.commit()

        return {"invalidated_count": invalidated_count}, 200

    def get_stats(self, simulation_id: Optional[int]):
        cursor = self.conn.cursor()

        if simulation_id:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    SUM(access_count) as total_accesses,
                    SUM(hit_count) as total_hits
                FROM cache_entries
                WHERE simulation_id = ?
                AND status = 'valid'
                """,
                (simulation_id,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    SUM(access_count) as total_accesses,
                    SUM(hit_count) as total_hits
                FROM cache_entries
                WHERE status = 'valid'
                """
            )

        row = cursor.fetchone()

        return {
            "total_entries": row["total_entries"] or 0,
            "total_accesses": row["total_accesses"] or 0,
            "total_hits": row["total_hits"] or 0,
        }, 200

    def health_check(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            return {"status": "healthy", "backend": "sqlite"}, 200
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}, 500


class PostgreSQLCacheBackend(CacheServiceBackend):
    """PostgreSQL backend for cache service."""

    def __init__(self, connection_string: str):
        import psycopg2
        import psycopg2.extras

        self.conn = psycopg2.connect(connection_string)
        psycopg2.extras.register_uuid()
        self._create_schema()

    def _create_schema(self):
        """Create cache database schema."""
        schema_path = (
            Path(__file__).parent.parent / "database" / "cache_service_schema.sql"
        )

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        cursor = self.conn.cursor()
        cursor.execute(schema_sql)
        self.conn.commit()
        logger.info("PostgreSQL cache schema created")

    def get(self, cache_key: str, session_id: str):
        cursor = self.conn.cursor()

        # Use the stored function for cache get
        cursor.execute(
            "SELECT * FROM get_cache_entry(%s, %s)", (cache_key, session_id)
        )

        row = cursor.fetchone()
        self.conn.commit()

        if row:
            return {
                "execution_id": row[0],
                "squid_id": row[1],
                "run_db_path": row[2],
                "metadata": row[3],
            }, 200
        else:
            return None, 404

    def set(self, data: dict, session_id: str):
        cursor = self.conn.cursor()

        # Use the stored function for cache set
        cursor.execute(
            """
            SELECT set_cache_entry(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data["cache_key"],
                data["simulation_id"],
                data["simulation_name"],
                data["simulation_version"],
                data["execution_id"],
                data["squid_id"],
                data["input_hash"],
                data["run_db_path"],
                session_id,
                data.get("ttl_seconds"),
                data.get("metadata"),
            ),
        )

        self.conn.commit()
        return {"success": True}, 200

    def invalidate(self, filters: dict, session_id: str):
        cursor = self.conn.cursor()

        # Use the stored function for invalidation
        cursor.execute(
            """
            SELECT invalidate_cache(%s, %s, %s, %s, %s, %s)
            """,
            (
                filters.get("simulation_id"),
                filters.get("simulation_name"),
                filters.get("simulation_version"),
                filters.get("pattern"),
                session_id,
                filters.get("reason"),
            ),
        )

        invalidated_count = cursor.fetchone()[0]
        self.conn.commit()

        return {"invalidated_count": invalidated_count}, 200

    def get_stats(self, simulation_id: Optional[int]):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT
                total_requests, total_hits, total_misses,
                hit_rate_percent, total_size_mb
            FROM cache_stats_summary
            WHERE simulation_id = %s OR %s IS NULL
            """,
            (simulation_id, simulation_id),
        )

        row = cursor.fetchone()

        if row:
            return {
                "total_requests": row[0],
                "total_hits": row[1],
                "total_misses": row[2],
                "hit_rate_percent": row[3],
                "total_size_mb": row[4],
            }, 200
        else:
            return {}, 200

    def health_check(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            return {"status": "healthy", "backend": "postgresql"}, 200
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}, 500


# REST API Endpoints
@app.route("/health", methods=["GET"])
def health():
    data, status = cache_db.health_check()
    return jsonify(data), status


@app.route("/cache/<path:cache_key>", methods=["GET"])
def get_cache(cache_key):
    session_id = request.headers.get("X-Session-ID", "demo-session")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401

    data, status = cache_db.get(cache_key, session_id)
    if data:
        return jsonify(data), status
    else:
        return jsonify({"error": "Not found"}), status


@app.route("/cache", methods=["POST"])
def set_cache():
    session_id = request.headers.get("X-Session-ID", "demo-session")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401

    data = request.json
    result, status = cache_db.set(data, session_id)
    return jsonify(result), status


@app.route("/cache/invalidate", methods=["POST"])
def invalidate_cache():
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return jsonify({"error": "Missing session ID"}), 401

    filters = request.json
    result, status = cache_db.invalidate(filters, session_id)
    return jsonify(result), status


@app.route("/cache/stats", methods=["GET"])
def get_stats():
    simulation_id = request.args.get("simulation_id", type=int)
    result, status = cache_db.get_stats(simulation_id)
    return jsonify(result), status


def main():
    parser = argparse.ArgumentParser(description="Sim2l Cache Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to listen on")
    parser.add_argument(
        "--backend",
        choices=["sqlite", "postgresql"],
        default="sqlite",
        help="Database backend",
    )
    parser.add_argument(
        "--db-path",
        default=str(Path.home() / ".sim2l" / "cache.db"),
        help="SQLite database path",
    )
    parser.add_argument(
        "--db-url", help="PostgreSQL connection string (for postgresql backend)"
    )
    parser.add_argument(
        "--no-auth", action="store_true", help="Disable authentication (demo mode)"
    )

    args = parser.parse_args()

    global cache_db
    global require_auth
    require_auth = not args.no_auth

    # Initialize backend
    if args.backend == "sqlite":
        cache_db = SQLiteCacheBackend(args.db_path)
        logger.info(f"Using SQLite backend: {args.db_path}")

        # Create a demo session that never expires when --no-auth is used
        if not require_auth:
            import sqlite3
            from datetime import datetime, timedelta
            conn = sqlite3.connect(args.db_path)
            cursor = conn.cursor()
            # Create session that expires in 100 years (effectively never)
            expires_at = (datetime.now() + timedelta(days=36500)).isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO cache_sessions (session_id, user_id, expires_at, access_level, is_valid)
                VALUES (?, ?, ?, ?, ?)
            """, ("demo-session", 1, expires_at, 'write', 1))
            conn.commit()
            conn.close()
            logger.info("Created demo session for no-auth mode")

    elif args.backend == "postgresql":
        if not args.db_url:
            logger.error("PostgreSQL backend requires --db-url")
            sys.exit(1)
        cache_db = PostgreSQLCacheBackend(args.db_url)
        logger.info("Using PostgreSQL backend")

    # Start server
    logger.info(f"Starting cache service on {args.host}:{args.port}")
    if not require_auth:
        logger.info("Authentication disabled (--no-auth mode)")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
