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

    def list_entries(self, limit=25, offset=0, simulation_id=None, simulation_name=None, status=None, session_id=None):
        """List cache entries with pagination and filters"""
        if not self._check_session(session_id):
            return {"error": "Unauthorized"}, 401

        cursor = self.conn.cursor()

        conditions = []
        params = []

        if simulation_id:
            conditions.append("simulation_id = ?")
            params.append(simulation_id)

        if simulation_name:
            conditions.append("simulation_name = ?")
            params.append(simulation_name)

        if status == 'valid':
            conditions.append("status = 'valid'")
        elif status == 'invalidated':
            conditions.append("status = 'invalidated'")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM cache_entries WHERE {where_clause}", params)
        total = cursor.fetchone()[0]

        # Get entries
        params.extend([limit, offset])
        cursor.execute(f"""
            SELECT
                cache_key, simulation_id, simulation_name, simulation_version,
                execution_id, squid_id, input_hash, created_at, last_accessed,
                access_count, hit_count, status
            FROM cache_entries
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, params)

        entries = []
        for row in cursor.fetchall():
            entries.append({
                "cache_key": row["cache_key"],
                "simulation_id": row["simulation_id"],
                "simulation_name": row["simulation_name"],
                "simulation_version": row["simulation_version"],
                "execution_id": row["execution_id"],
                "squid_id": row["squid_id"],
                "input_hash": row["input_hash"],
                "created_at": row["created_at"],
                "last_accessed_at": row["last_accessed"],
                "access_count": row["access_count"],
                "hit_count": row["hit_count"],
                "status": row["status"]
            })

        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset
        }, 200


class PostgreSQLCacheBackend(CacheServiceBackend):
    """PostgreSQL backend for cache service."""

    def __init__(self, connection_string: str, no_auth: bool = False):
        import psycopg2
        import psycopg2.extras

        self.conn = psycopg2.connect(connection_string)
        psycopg2.extras.register_uuid()
        self.no_auth = no_auth
        self._create_schema()

        # Create demo session if running in no-auth mode
        if self.no_auth:
            self._create_demo_session()

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

    def _create_demo_session(self):
        """Create demo session for no-auth mode."""
        cursor = self.conn.cursor()

        # Check if demo-session already exists
        cursor.execute(
            "SELECT session_id FROM cache_sessions WHERE session_id = 'demo-session'"
        )
        if cursor.fetchone():
            logger.debug("Demo session already exists")
            return

        # Create demo session with write privileges
        cursor.execute(
            """
            INSERT INTO cache_sessions (session_id, user_id, expires_at, access_level, is_valid)
            VALUES ('demo-session', 0, '2099-12-31 23:59:59', 'write', true)
            ON CONFLICT (session_id) DO NOTHING
            """
        )
        self.conn.commit()
        logger.info("Created demo session for no-auth mode")

    def get(self, cache_key: str, session_id: str):
        cursor = self.conn.cursor()

        logger.debug(f"PostgreSQL: Getting cache entry - Key: {cache_key}, Session: {session_id}")
        # Use the stored function for cache get
        cursor.execute(
            "SELECT * FROM get_cache_entry(%s, %s)", (cache_key, session_id)
        )

        row = cursor.fetchone()
        self.conn.commit()

        if row:
            logger.debug(f"PostgreSQL: Cache entry found - Execution ID: {row[0]}")
            return {
                "execution_id": row[0],
                "squid_id": row[1],
                "run_db_path": row[2],
                "metadata": row[3],
            }, 200
        else:
            logger.debug(f"PostgreSQL: Cache entry not found - Key: {cache_key}")
            return None, 404

    def set(self, data: dict, session_id: str):
        import json
        cursor = self.conn.cursor()

        logger.debug(f"PostgreSQL: Setting cache entry - Key: {data.get('cache_key')}, Session: {session_id}")
        logger.debug(f"PostgreSQL: Cache data - Sim: {data.get('simulation_name')}, Exec: {data.get('execution_id')}")

        # Convert metadata dict to JSON string for PostgreSQL JSONB
        metadata = data.get("metadata")
        if metadata is not None and isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        # Use the stored function for cache set
        try:
            cursor.execute(
                """
                SELECT set_cache_entry(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
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
                    metadata,
                ),
            )

            self.conn.commit()
            logger.debug(f"PostgreSQL: Successfully stored cache entry - Key: {data.get('cache_key')}")
            return {"success": True}, 200
        except Exception as e:
            self.conn.rollback()
            logger.error(f"PostgreSQL: Error setting cache entry: {e}", exc_info=True)
            raise

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

        # First try the cache_stats_summary view
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

        if row and row[0] is not None:
            return {
                "total_requests": row[0],
                "total_hits": row[1],
                "total_misses": row[2],
                "hit_rate_percent": row[3],
                "total_size_mb": row[4],
            }, 200

        # Fallback: calculate stats directly from cache_entries table
        if simulation_id:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    SUM(access_count) as total_accesses,
                    SUM(hit_count) as total_hits,
                    SUM(size_bytes) as total_size_bytes
                FROM cache_entries
                WHERE simulation_id = %s
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
                    SUM(hit_count) as total_hits,
                    SUM(size_bytes) as total_size_bytes
                FROM cache_entries
                WHERE status = 'valid'
                """
            )

        row = cursor.fetchone()

        if row:
            total_entries = row[0] or 0
            total_accesses = row[1] or 0
            total_hits = row[2] or 0
            total_size_bytes = row[3] or 0

            hit_rate = (total_hits / total_accesses * 100) if total_accesses > 0 else 0

            return {
                "total_entries": total_entries,
                "total_accesses": total_accesses,
                "total_hits": total_hits,
                "hit_rate_percent": round(hit_rate, 2),
                "total_size_mb": round(total_size_bytes / (1024 * 1024), 2) if total_size_bytes else 0,
            }, 200
        else:
            return {
                "total_entries": 0,
                "total_accesses": 0,
                "total_hits": 0,
                "hit_rate_percent": 0,
                "total_size_mb": 0,
            }, 200

    def health_check(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            return {"status": "healthy", "backend": "postgresql"}, 200
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}, 500

    def list_entries(self, limit=25, offset=0, simulation_id=None, simulation_name=None, status=None, session_id=None):
        """List cache entries with pagination and filters"""
        cursor = self.conn.cursor()

        conditions = []
        params = []

        if simulation_id:
            conditions.append("simulation_id = %s")
            params.append(simulation_id)

        if simulation_name:
            conditions.append("simulation_name = %s")
            params.append(simulation_name)

        if status == 'valid':
            conditions.append("status = %s")
            params.append('valid')
        elif status == 'invalidated':
            conditions.append("status = %s")
            params.append('invalidated')

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM cache_entries WHERE {where_clause}", params)
        total = cursor.fetchone()[0]

        # Get entries
        params.extend([limit, offset])
        cursor.execute(f"""
            SELECT
                cache_key, simulation_id, simulation_name, simulation_version,
                execution_id, squid_id, input_hash, created_at, last_accessed,
                access_count, hit_count, size_bytes, status
            FROM cache_entries
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params)

        entries = []
        for row in cursor.fetchall():
            entries.append({
                "cache_key": row[0],
                "simulation_id": row[1],
                "simulation_name": row[2],
                "simulation_version": row[3],
                "execution_id": row[4],
                "squid_id": row[5],
                "input_hash": row[6],
                "created_at": str(row[7]),
                "last_accessed_at": str(row[8]) if row[8] else None,
                "access_count": row[9],
                "hit_count": row[10],
                "size_bytes": row[11],
                "status": row[12]
            })

        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset
        }, 200


# REST API Endpoints
@app.route("/health", methods=["GET"])
def health():
    data, status = cache_db.health_check()
    return jsonify(data), status


@app.route("/cache/<path:cache_key>", methods=["GET"])
def get_cache(cache_key):
    session_id = request.headers.get("X-Session-ID", "demo-session")
    logger.debug(f"GET /cache/{cache_key} - Session: {session_id}")
    if require_auth and not session_id:
        logger.warning(f"Missing session ID for cache key: {cache_key}")
        return jsonify({"error": "Missing session ID"}), 401

    data, status = cache_db.get(cache_key, session_id)
    if data:
        logger.debug(f"Cache hit for key: {cache_key}")
        return jsonify(data), status
    else:
        logger.debug(f"Cache miss for key: {cache_key}")
        return jsonify({"error": "Not found"}), status


@app.route("/cache", methods=["POST"])
def set_cache():
    session_id = request.headers.get("X-Session-ID", "demo-session")
    logger.debug(f"POST /cache - Session: {session_id}")
    if require_auth and not session_id:
        logger.warning("Missing session ID for cache set")
        return jsonify({"error": "Missing session ID"}), 401

    data = request.json
    logger.debug(f"Setting cache entry: {data.get('cache_key', 'unknown')}")
    try:
        result, status = cache_db.set(data, session_id)
        if status == 200:
            logger.debug(f"Successfully stored cache entry: {data.get('cache_key', 'unknown')}")
        else:
            logger.warning(f"Failed to store cache entry: {data.get('cache_key', 'unknown')} - Status: {status}")
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error storing cache entry: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


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


@app.route("/cache/entries", methods=["GET"])
def list_cache_entries():
    """List all cache entries with pagination and filters"""
    session_id = request.headers.get("X-Session-ID", "demo-session")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401

    limit = request.args.get("limit", 25, type=int)
    offset = request.args.get("offset", 0, type=int)
    simulation_id = request.args.get("simulation_id", type=int)
    simulation_name = request.args.get("simulation_name")
    status = request.args.get("status")  # 'valid' or 'invalidated'

    try:
        result, http_status = cache_db.list_entries(
            limit=limit,
            offset=offset,
            simulation_id=simulation_id,
            simulation_name=simulation_name,
            status=status,
            session_id=session_id
        )
        return jsonify(result), http_status
    except Exception as e:
        logger.error(f"Error listing cache entries: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
    parser.add_argument(
        "--debug", action="store_true", help="Enable DEBUG logging"
    )

    args = parser.parse_args()

    # Set logging level based on --debug flag
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            force=True
        )
        logger.setLevel(logging.DEBUG)
        logger.debug("DEBUG logging enabled")

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
        cache_db = PostgreSQLCacheBackend(args.db_url, no_auth=not require_auth)
        logger.info("Using PostgreSQL backend")

    # Start server
    logger.info(f"Starting cache service on {args.host}:{args.port}")
    if not require_auth:
        logger.info("Authentication disabled (--no-auth mode)")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
