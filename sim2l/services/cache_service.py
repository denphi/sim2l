# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Standalone cache service for distributed caching.

Provides REST API for cache operations with session-based authentication.
Supports both SQLite (default) and PostgreSQL backends.
"""

import os
import sys
import argparse
import logging
import json
import threading
from datetime import datetime, timedelta

# Shared service helpers (see sim2l/services/_common.py).
from sim2l.services._common import (
    LoginRateLimiter,
    adapt_postgres_schema_for_sqlite as _adapt_postgres_schema_for_sqlite,
    client_ip as _client_ip,
    extract_session_id as _extract_session_id,
    serve_app,
    utcnow as _utcnow,
)

# Review item #T15: per-(ip, username) login throttle. See catalog_service
# for the full rationale; same instance can't be shared across services
# because each service is its own Flask app.
_login_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60.0)
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# Database backend (will be initialized in main)
cache_db = None
require_auth = True  # Set to False with --no-auth flag

MAX_PAGE_SIZE = 1000  # Hard upper bound for list pagination


@app.teardown_appcontext
def _close_db_connection(exc):
    """Close the per-thread SQLite/PostgreSQL connection at end of each request."""
    if cache_db is not None and hasattr(cache_db, '_local'):
        conn = getattr(cache_db._local, 'conn', None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            cache_db._local.conn = None


def adapt_postgres_schema_for_sqlite(schema_sql: str) -> str:
    """Cache-service-specific adapter for PostgreSQL → SQLite schema SQL.

    Delegates to the shared helper with cache-specific options: only restore
    ``IF NOT EXISTS`` on tables whose names start with ``cache_``, and strip
    only function/view blocks (the cache schema has no triggers).
    """
    return _adapt_postgres_schema_for_sqlite(
        schema_sql,
        restore_if_not_exists_prefix="cache_",
    )


class CacheServiceBackend:
    """Abstract backend for cache service."""

    def get(self, cache_key: str, session_id: str):
        raise NotImplementedError

    def set(self, data: dict, session_id: str):
        raise NotImplementedError

    def invalidate(self, filters: dict, session_id: str):
        raise NotImplementedError

    def delete(self, cache_key: str, session_id: str):
        raise NotImplementedError

    def get_stats(self, simulation_id: Optional[int]):
        raise NotImplementedError

    def health_check(self):
        raise NotImplementedError

    def mirror_session(self, session) -> None:
        """Insert/refresh a session row in the backend's session table.

        Used by ``/session/login`` to bridge an authenticated
        ``SessionManager.Session`` instance into the cache service's
        ``cache_sessions`` table so subsequent requests are accepted.
        Review item #T1.
        """
        raise NotImplementedError


class SQLiteCacheBackend(CacheServiceBackend):
    """SQLite backend for cache service.

    Uses a per-thread connection pool (threading.local) so that concurrent
    Flask requests each get their own SQLite connection, avoiding
    'OperationalError: database is locked' errors under load.
    WAL journal mode is enabled for better read concurrency.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._schema_lock = threading.Lock()
        self._create_schema()

    def _get_conn(self):
        """Return the per-thread SQLite connection, creating it if needed."""
        import sqlite3
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            # Enable FK enforcement so the schema's CASCADEs actually fire.
            # Review item #C5.
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def _create_schema(self):
        """Create cache database schema (run once on the initializing thread)."""
        schema_path = (
            Path(__file__).parent.parent / "database" / "cache_service_schema.sql"
        )

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        schema_sql = adapt_postgres_schema_for_sqlite(schema_sql)

        with self._schema_lock:
            conn = self._get_conn()
            try:
                conn.executescript(schema_sql)
                conn.commit()
                logger.info("SQLite cache schema created")
            except Exception as e:
                logger.error(f"Failed to create schema: {e}")

    def _check_session(self, session_id: str) -> bool:
        """Check if session is valid."""
        conn = self._get_conn()
        cursor = conn.cursor()
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

    def _check_write_session(self, session_id: str) -> bool:
        """Check the session has write/admin access, not merely that it exists.

        Mirrors ``PostgreSQLCacheBackend._check_write_session``. Its absence here
        meant the same endpoint enforced different authorization depending on
        which backend the service was started with: on PostgreSQL, destructive
        cache operations required write/admin; on SQLite — the default in
        ``start_services.sh`` and the Docker images — any valid session passed,
        so a ``role="user"`` account holding only ``["read", "write"]``
        privileges could clear the entire cache. The ``access_level`` column was
        already in the SQLite schema; nothing consulted it.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM cache_sessions
            WHERE session_id = ?
            AND is_valid = 1
            AND expires_at > datetime('now')
            AND access_level IN ('write', 'admin')
            """,
            (session_id,),
        )
        return cursor.fetchone() is not None

    def mirror_session(self, session) -> None:
        access_level = "admin" if "admin" in session.privileges else (
            "write" if "write" in session.privileges else "read"
        )
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO cache_sessions (
                session_id, user_id, expires_at, access_level, is_valid
            ) VALUES (?, ?, ?, ?, 1)
            """,
            (
                session.session_id,
                session.user_id,
                session.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                access_level,
            ),
        )
        conn.commit()

    def get(self, cache_key: str, session_id: str):
        if not self._check_session(session_id):
            return None, 401

        conn = self._get_conn()
        cursor = conn.cursor()

        # Wrap the increment + select in a single write transaction so two
        # concurrent gets cannot interleave UPDATE/SELECT pairs. BEGIN IMMEDIATE
        # acquires the write lock up-front, which (under WAL) blocks other
        # writers but lets readers proceed.
        cursor.execute("BEGIN IMMEDIATE")
        try:
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
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if row:
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

        conn = self._get_conn()
        cursor = conn.cursor()

        # Compute expires_at in Python to avoid SQL injection via f-string formatting.
        # Use space separator (not T) so SQLite's datetime('now') comparison works.
        expires_at = None
        if data.get("ttl_seconds") is not None and data["ttl_seconds"] != "":
            expires_at = (
                _utcnow() + timedelta(seconds=int(data["ttl_seconds"]))
            ).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            INSERT OR REPLACE INTO cache_entries (
                cache_key, simulation_id, simulation_name, simulation_version,
                execution_id, squid_id, input_hash, run_db_path,
                expires_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                expires_at,
                json.dumps(data.get("metadata")) if data.get("metadata") else None,
            ),
        )

        conn.commit()
        return {"success": True}, 200

    def invalidate(self, filters: dict, session_id: str):
        if not self._check_session(session_id):
            return {"error": "Unauthorized"}, 401

        # Build (clause, param) pairs in lockstep to prevent misalignment
        clauses = ["status = 'valid'"]
        params = []

        if filters.get("simulation_id"):
            clauses.append("simulation_id = ?")
            params.append(filters["simulation_id"])

        if filters.get("simulation_name"):
            clauses.append("simulation_name = ?")
            params.append(filters["simulation_name"])

        if filters.get("simulation_version"):
            clauses.append("simulation_version = ?")
            params.append(filters["simulation_version"])

        if filters.get("pattern"):
            clauses.append("cache_key LIKE ?")
            params.append(filters["pattern"])

        # Join known-safe clause strings (no user data embedded)
        where_sql = " AND ".join(clauses)

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE cache_entries SET status = 'invalidated' WHERE {where_sql}",
            params,
        )

        invalidated_count = cursor.rowcount
        conn.commit()

        return {"invalidated_count": invalidated_count}, 200

    def delete(self, cache_key: str, session_id: str):
        if not self._check_session(session_id):
            return {"error": "Unauthorized"}, 401

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count == 0:
            return {"error": "Not found"}, 404

        return {"deleted_count": deleted_count, "cache_key": cache_key}, 200

    def get_stats(self, simulation_id: Optional[int]):
        conn = self._get_conn()
        cursor = conn.cursor()

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
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return {"status": "healthy", "backend": "sqlite"}, 200
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {"status": "unhealthy", "error": "Internal error"}, 500

    def delete_all(self, session_id: str) -> int:
        """Delete all cache entries. Returns count of deleted rows.

        Requires write/admin, matching the PostgreSQL backend.
        """
        if not self._check_write_session(session_id):
            raise PermissionError("Unauthorized")
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache_entries")
        deleted = cursor.rowcount
        conn.commit()
        return deleted

    def list_entries(self, limit=25, offset=0, simulation_id=None, simulation_name=None, status=None, session_id=None):
        """List cache entries with pagination and filters."""
        if not self._check_session(session_id):
            return {"error": "Unauthorized"}, 401

        limit = min(limit, MAX_PAGE_SIZE)

        conn = self._get_conn()
        cursor = conn.cursor()

        conditions = []
        params = []

        if simulation_id:
            conditions.append("simulation_id = ?")
            params.append(simulation_id)

        if simulation_name:
            conditions.append("simulation_name = ?")
            params.append(simulation_name)

        if status == "valid":
            conditions.append("status = 'valid'")
        elif status == "invalidated":
            conditions.append("status = 'invalidated'")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(f"SELECT COUNT(*) FROM cache_entries WHERE {where_clause}", params)
        total = cursor.fetchone()[0]

        params.extend([limit, offset])
        cursor.execute(
            f"""
            SELECT
                cache_key, simulation_id, simulation_name, simulation_version,
                execution_id, squid_id, input_hash, created_at, last_accessed,
                access_count, hit_count, status, metadata
            FROM cache_entries
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )

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
                "status": row["status"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            })

        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }, 200


class PostgreSQLCacheBackend(CacheServiceBackend):
    """PostgreSQL backend for cache service.

    Uses a per-thread connection pool (threading.local) for thread safety
    under concurrent Flask requests.
    """

    def __init__(self, connection_string: str, no_auth: bool = False):
        self.connection_string = connection_string
        self._local = threading.local()
        self.no_auth = no_auth
        self._create_schema()

        if self.no_auth:
            self._create_demo_session()

    def _get_conn(self):
        """Return the per-thread PostgreSQL connection, creating it if needed."""
        import psycopg2
        import psycopg2.extras

        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed:
            conn = psycopg2.connect(self.connection_string)
            psycopg2.extras.register_uuid()
            self._local.conn = conn
        return conn

    def _create_schema(self):
        """Create cache database schema."""
        schema_path = (
            Path(__file__).parent.parent / "database" / "cache_service_schema.sql"
        )

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        logger.info("PostgreSQL cache schema created")

    def _create_demo_session(self):
        """Create demo session for no-auth mode."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT session_id FROM cache_sessions WHERE session_id = 'demo-session'"
        )
        if cursor.fetchone():
            logger.debug("Demo session already exists")
            return

        cursor.execute(
            """
            INSERT INTO cache_sessions (session_id, user_id, expires_at, access_level, is_valid)
            VALUES ('demo-session', 0, '2099-12-31 23:59:59', 'write', true)
            ON CONFLICT (session_id) DO NOTHING
            """
        )
        conn.commit()
        logger.info("Created demo session for no-auth mode")

    def _check_write_session(self, session_id: str) -> bool:
        """Check if the session has write/admin access."""
        cursor = self._get_conn().cursor()
        cursor.execute(
            """
            SELECT 1
            FROM cache_sessions
            WHERE session_id = %s
              AND is_valid = true
              AND expires_at > CURRENT_TIMESTAMP
              AND access_level IN ('write', 'admin')
            """,
            (session_id,),
        )
        return cursor.fetchone() is not None

    def mirror_session(self, session) -> None:
        access_level = "admin" if "admin" in session.privileges else (
            "write" if "write" in session.privileges else "read"
        )
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cache_sessions (
                session_id, user_id, expires_at, access_level, is_valid
            ) VALUES (%s, %s, %s, %s, true)
            ON CONFLICT (session_id) DO UPDATE SET
                expires_at = EXCLUDED.expires_at,
                access_level = EXCLUDED.access_level,
                is_valid = true
            """,
            (
                session.session_id,
                session.user_id,
                session.expires_at,
                access_level,
            ),
        )
        conn.commit()

    def get(self, cache_key: str, session_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()

        logger.debug(f"PostgreSQL: Getting cache entry - Key: {cache_key}, Session: {session_id}")
        cursor.execute(
            "SELECT * FROM get_cache_entry(%s, %s)", (cache_key, session_id)
        )

        row = cursor.fetchone()
        conn.commit()

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

        conn = self._get_conn()
        cursor = conn.cursor()

        logger.debug(f"PostgreSQL: Setting cache entry - Key: {data.get('cache_key')}, Session: {session_id}")

        metadata = data.get("metadata")
        if metadata is not None and isinstance(metadata, dict):
            metadata = json.dumps(metadata)

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

            conn.commit()
            logger.debug(f"PostgreSQL: Successfully stored cache entry - Key: {data.get('cache_key')}")
            return {"success": True}, 200
        except Exception as e:
            conn.rollback()
            logger.error(f"PostgreSQL: Error setting cache entry: {e}", exc_info=True)
            raise

    def invalidate(self, filters: dict, session_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()

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
        conn.commit()

        return {"invalidated_count": invalidated_count}, 200

    def delete(self, cache_key: str, session_id: str):
        if not self._check_write_session(session_id):
            return {"error": "Unauthorized"}, 401

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache_entries WHERE cache_key = %s", (cache_key,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count == 0:
            return {"error": "Not found"}, 404

        return {"deleted_count": deleted_count, "cache_key": cache_key}, 200

    def get_stats(self, simulation_id: Optional[int]):
        conn = self._get_conn()
        cursor = conn.cursor()

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
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return {"status": "healthy", "backend": "postgresql"}, 200
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {"status": "unhealthy", "error": "Internal error"}, 500

    def delete_all(self, session_id: str) -> int:
        """Delete all cache entries. Returns count of deleted rows."""
        if not self._check_write_session(session_id):
            raise PermissionError("Unauthorized")
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache_entries")
        deleted = cursor.rowcount
        conn.commit()
        return deleted

    def list_entries(self, limit=25, offset=0, simulation_id=None, simulation_name=None, status=None, session_id=None):
        """List cache entries with pagination and filters."""
        limit = min(limit, MAX_PAGE_SIZE)

        conn = self._get_conn()
        cursor = conn.cursor()

        conditions = []
        params = []

        if simulation_id:
            conditions.append("simulation_id = %s")
            params.append(simulation_id)

        if simulation_name:
            conditions.append("simulation_name = %s")
            params.append(simulation_name)

        if status == "valid":
            conditions.append("status = %s")
            params.append("valid")
        elif status == "invalidated":
            conditions.append("status = %s")
            params.append("invalidated")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(f"SELECT COUNT(*) FROM cache_entries WHERE {where_clause}", params)
        total = cursor.fetchone()[0]

        params.extend([limit, offset])
        cursor.execute(
            f"""
            SELECT
                cache_key, simulation_id, simulation_name, simulation_version,
                execution_id, squid_id, input_hash, created_at, last_accessed,
                access_count, hit_count, size_bytes, status, metadata
            FROM cache_entries
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )

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
                "status": row[12],
                "metadata": row[13] if row[13] else None,
            })

        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }, 200


# REST API Endpoints
@app.route("/health", methods=["GET"])
def health():
    data, status = cache_db.health_check()
    return jsonify(data), status


@app.route("/session/login", methods=["POST"])
def login():
    """Authenticate and register a session row in ``cache_sessions``.

    Review item #T1: cache_service has its own session table separate from
    the catalog's, so a session created via the catalog's /session/login is
    not recognised here. Web clients call this endpoint with the same
    credentials to get a cache-service session id.
    """
    from sim2l.database.session_manager import get_session_manager

    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    ip = _client_ip(request)
    if not _login_limiter.allow(ip, username):
        return jsonify({
            "error": "Too many login attempts. Please wait a minute and try again."
        }), 429

    try:
        session = get_session_manager().authenticate(username, password)
    except ValueError:
        return jsonify({"error": "Invalid username or password"}), 401

    _login_limiter.reset(ip, username)

    # Mirror into the backend's session table so subsequent requests succeed.
    try:
        cache_db.mirror_session(session)
    except Exception as exc:
        logger.warning("Could not mirror session into cache_sessions: %s", exc)
        return jsonify({"error": "Internal server error"}), 500

    return jsonify({
        "token": session.session_id,
        "session_id": session.session_id,
        "username": session.username,
        "expires_at": session.expires_at.isoformat(),
    }), 200


@app.route("/cache/<path:cache_key>", methods=["GET"])
def get_cache(cache_key):
    session_id, err = _extract_session_id(request, require_auth=require_auth)
    if err is not None:
        logger.warning(f"Missing session ID for cache key: {cache_key}")
        body, status = err
        return jsonify(body), status

    logger.debug(f"GET /cache/{cache_key} - Session: {session_id}")

    data, status = cache_db.get(cache_key, session_id)
    if data:
        logger.debug(f"Cache hit for key: {cache_key}")
        return jsonify(data), status
    else:
        logger.debug(f"Cache miss for key: {cache_key}")
        return jsonify({"error": "Not found"}), status


@app.route("/cache/<path:cache_key>", methods=["DELETE"])
def delete_cache(cache_key):
    session_id, err = _extract_session_id(request, require_auth=require_auth)
    if err is not None:
        logger.warning(f"Missing session ID for cache delete: {cache_key}")
        body, status = err
        return jsonify(body), status

    result, status = cache_db.delete(cache_key, session_id)
    return jsonify(result), status


@app.route("/cache", methods=["DELETE"])
def clear_all_cache():
    session_id, err = _extract_session_id(request, require_auth=require_auth)
    if err is not None:
        body, status = err
        return jsonify(body), status

    try:
        deleted = cache_db.delete_all(session_id)
        return jsonify({"deleted": deleted}), 200
    except Exception as exc:
        logger.error(f"Clear all cache failed: {exc}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/cache", methods=["POST"])
def set_cache():
    session_id, err = _extract_session_id(request, require_auth=require_auth)
    if err is not None:
        logger.warning("Missing session ID for cache set")
        body, status = err
        return jsonify(body), status

    logger.debug(f"POST /cache - Session: {session_id}")

    data = request.json
    logger.debug(f"Setting cache entry: {data.get('cache_key', 'unknown')}")
    try:
        result, status = cache_db.set(data, session_id)
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error storing cache entry: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/cache/invalidate", methods=["POST"])
def invalidate_cache():
    # /cache/invalidate requires an authenticated header even in dev mode —
    # don't fall back to demo-session because invalidation is destructive.
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
    """List all cache entries with pagination and filters."""
    session_id, err = _extract_session_id(request, require_auth=require_auth)
    if err is not None:
        body, status = err
        return jsonify(body), status

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
            session_id=session_id,
        )
        return jsonify(result), http_status
    except Exception as e:
        logger.error(f"Error listing cache entries: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


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

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            force=True,
        )
        logger.setLevel(logging.DEBUG)
        logger.debug("DEBUG logging enabled")

    global cache_db
    global require_auth
    require_auth = not args.no_auth

    if args.backend == "sqlite":
        cache_db = SQLiteCacheBackend(args.db_path)
        logger.info(f"Using SQLite backend: {args.db_path}")

        if not require_auth:
            import sqlite3
            conn = sqlite3.connect(args.db_path)
            cursor = conn.cursor()
            expires_at = (_utcnow() + timedelta(days=36500)).isoformat()
            cursor.execute(
                """
                INSERT OR REPLACE INTO cache_sessions (session_id, user_id, expires_at, access_level, is_valid)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("demo-session", 1, expires_at, "write", 1),
            )
            conn.commit()
            conn.close()
            logger.info("Created demo session for no-auth mode")

    elif args.backend == "postgresql":
        if not args.db_url:
            logger.error("PostgreSQL backend requires --db-url")
            sys.exit(1)
        cache_db = PostgreSQLCacheBackend(args.db_url, no_auth=not require_auth)
        logger.info("Using PostgreSQL backend")

    logger.info(f"Starting cache service on {args.host}:{args.port}")
    if not require_auth:
        logger.info("Authentication disabled (--no-auth mode)")
    # Production WSGI server when available; see _common.serve_app.
    serve_app(app, args.host, args.port, "cache")


if __name__ == "__main__":
    main()
