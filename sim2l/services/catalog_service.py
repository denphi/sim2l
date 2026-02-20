"""
Standalone catalog service for simulation registry.

Provides REST API for tool discovery, registration, and statistics
with session-based authentication. Supports both SQLite and PostgreSQL.
"""

import os
import sys
import argparse
import logging
import threading
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Database backend (initialized in main)
catalog_db = None
# Authentication configuration (set by --no-auth flag)
require_auth = True


def _adapt_catalog_schema_for_sqlite(schema_sql: str) -> str:
    """Convert a PostgreSQL catalog schema to SQLite-compatible SQL.

    Handles type substitutions and strips PostgreSQL-specific constructs
    (functions, views, triggers) that SQLite doesn't support.
    """
    schema_sql = schema_sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    schema_sql = schema_sql.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    schema_sql = schema_sql.replace("JSONB", "TEXT")
    schema_sql = schema_sql.replace("BIGINT", "INTEGER")
    schema_sql = schema_sql.replace("BOOLEAN", "INTEGER")
    schema_sql = schema_sql.replace("DEFAULT true", "DEFAULT 1")
    schema_sql = schema_sql.replace("DEFAULT false", "DEFAULT 0")
    schema_sql = schema_sql.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")

    # Remove PostgreSQL-specific blocks using $$ delimiter tracking
    lines = schema_sql.split("\n")
    filtered_lines = []
    skip_until_end = False
    paren_depth = 0

    for line in lines:
        if any(x in line for x in [
            "CREATE OR REPLACE FUNCTION",
            "CREATE OR REPLACE VIEW",
            "CREATE TRIGGER",
        ]):
            skip_until_end = True
            paren_depth = 0

        if skip_until_end:
            if "$$" in line:
                if paren_depth == 0:
                    paren_depth = 1
                else:
                    paren_depth = 0
                    skip_until_end = False
            elif line.rstrip().endswith(";") and paren_depth == 0:
                skip_until_end = False
            continue

        stripped = line.strip()
        if stripped and not skip_until_end:
            filtered_lines.append(line)

    schema_sql = "\n".join(filtered_lines)
    # Restore IF NOT EXISTS for table creation
    schema_sql = schema_sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
    return schema_sql


class CatalogServiceBackend:
    """Abstract backend for catalog service."""

    def search(self, query, tags, status, limit):
        raise NotImplementedError

    def get_simulation(self, name, version):
        raise NotImplementedError

    def register_simulation(self, data, session_id):
        raise NotImplementedError

    def update_simulation(self, simulation_id, updates, session_id):
        raise NotImplementedError

    def record_execution(self, data):
        raise NotImplementedError

    def get_stats(self, simulation_id):
        raise NotImplementedError

    def sync_pending_requests(self, installation_id):
        raise NotImplementedError

    def approve_sync(self, request_id, session_id):
        raise NotImplementedError

    def get_overview_stats(self):
        raise NotImplementedError

    def health_check(self):
        raise NotImplementedError


class SQLiteCatalogBackend(CatalogServiceBackend):
    """SQLite backend for catalog service.

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
            self._local.conn = conn
        return conn

    def _create_schema(self):
        """Create catalog database schema (run once on the initializing thread)."""
        schema_path = (
            Path(__file__).parent.parent / "database" / "master_catalog_schema.sql"
        )

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        schema_sql = _adapt_catalog_schema_for_sqlite(schema_sql)

        with self._schema_lock:
            conn = self._get_conn()
            try:
                conn.executescript(schema_sql)
                conn.commit()
                logger.info("SQLite catalog schema created")
            except Exception as e:
                logger.error(f"Failed to create schema: {e}")

    def _check_session(self, session_id: str) -> bool:
        """Check if session is valid."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM sessions
            WHERE session_id = ?
            AND is_valid = 1
            AND expires_at > datetime('now')
            """,
            (session_id,),
        )
        return cursor.fetchone() is not None

    def _check_privilege(self, session_id: str, privilege: str) -> bool:
        """Check if session has privilege."""
        # Allow no-auth-session to have all privileges
        if session_id == "no-auth-session":
            return True

        import json
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT privileges FROM sessions
            WHERE session_id = ?
            AND is_valid = 1
            AND expires_at > datetime('now')
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False

        privileges = json.loads(row["privileges"]) if row["privileges"] else []
        return privilege in privileges or "admin" in privileges

    def search(self, query, tags, status, limit):
        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        conditions = []
        params = []

        if query:
            conditions.append("name LIKE ?")
            params.append(f"%{query}%")

        if status and status != "all":
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(
            f"""
            SELECT id, name, version, description, author, tags, status,
                   created_at, updated_at
            FROM simulations
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params + [limit],
        )

        results = []
        for row in cursor.fetchall():
            sim = dict(row)
            sim["tags"] = json.loads(sim["tags"]) if sim["tags"] else []

            # Filter by tags if specified
            if tags:
                sim_tags = set(sim["tags"])
                if not sim_tags.intersection(set(tags)):
                    continue

            results.append(sim)

        return results, 200

    def get_simulation(self, name, version):
        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        if version:
            cursor.execute(
                """
                SELECT * FROM simulations
                WHERE name = ? AND version = ?
                """,
                (name, version),
            )
        else:
            # Get latest version
            cursor.execute(
                """
                SELECT * FROM simulations
                WHERE name = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (name,),
            )

        row = cursor.fetchone()
        if not row:
            return None, 404

        sim = dict(row)
        for field in ["tags", "input_schema", "output_schema", "dependencies", "metadata"]:
            if sim.get(field):
                sim[field] = json.loads(sim[field])

        return sim, 200

    def register_simulation(self, data, session_id):
        import json

        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        conn = self._get_conn()
        cursor = conn.cursor()

        if session_id == "no-auth-session":
            user_id = None
        else:
            cursor.execute(
                "SELECT user_id FROM sessions WHERE session_id = ?", (session_id,)
            )
            user_row = cursor.fetchone()
            user_id = user_row["user_id"] if user_row else None

        cursor.execute(
            "SELECT id FROM simulations WHERE name = ? AND version = ?",
            (data["name"], data["version"]),
        )
        if cursor.fetchone():
            return {"error": "Simulation already registered"}, 409

        cursor.execute(
            """
            INSERT INTO simulations (
                name, version, description, author, author_email,
                organization, license, repository_url, documentation_url,
                tags, input_schema, output_schema, workflow_type,
                workflow_hash, dependencies, python_version, status,
                visibility, created_by, updated_by, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["version"],
                data.get("description"),
                data.get("author"),
                data.get("author_email"),
                data.get("organization"),
                data.get("license"),
                data.get("repository_url"),
                data.get("documentation_url"),
                json.dumps(data.get("tags", [])),
                json.dumps(data.get("input_schema")),
                json.dumps(data.get("output_schema")),
                data.get("workflow_type", "notebook"),
                data.get("workflow_hash"),
                json.dumps(data.get("dependencies", [])),
                data.get("python_version"),
                "active",
                data.get("visibility", "public"),
                user_id,
                user_id,
                json.dumps(data.get("metadata")),
            ),
        )

        simulation_id = cursor.lastrowid
        conn.commit()

        logger.info(f"Registered simulation {data['name']}/{data['version']} (ID: {simulation_id})")
        return {"id": simulation_id, "status": "registered"}, 201

    def update_simulation(self, simulation_id, updates, session_id):
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        set_clauses = []
        params = []

        for key, value in updates.items():
            if key in ["tags", "dependencies", "metadata", "input_schema", "output_schema"]:
                set_clauses.append(f"{key} = ?")
                params.append(json.dumps(value))
            elif key in ["description", "status", "visibility", "license"]:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        if not set_clauses:
            return {"error": "No valid fields to update"}, 400

        set_clauses.append("updated_at = datetime('now')")
        params.append(simulation_id)

        cursor.execute(
            f"UPDATE simulations SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )

        conn.commit()
        return {"status": "updated"}, 200

    def record_execution(self, data):
        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO execution_registry (
                execution_id, squid_id, simulation_id, user_id,
                started_at, completed_at, duration_seconds, status,
                executor_type, cache_hit, run_db_path, run_db_size_bytes,
                input_hash, output_count, artifact_count,
                error_count, warning_count, environment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["execution_id"],
                data["squid_id"],
                data["simulation_id"],
                data.get("user_id"),
                data["started_at"],
                data.get("completed_at"),
                data.get("duration_seconds"),
                data["status"],
                data["executor_type"],
                data.get("cache_hit", False),
                data.get("run_db_path"),
                data.get("run_db_size_bytes"),
                data.get("input_hash"),
                data.get("output_count", 0),
                data.get("artifact_count", 0),
                data.get("error_count", 0),
                data.get("warning_count", 0),
                json.dumps(data.get("environment")),
            ),
        )

        conn.commit()
        return {"status": "recorded"}, 201

    def get_stats(self, simulation_id):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(*) as total_executions,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) as cached,
                AVG(duration_seconds) as avg_duration,
                MIN(duration_seconds) as min_duration,
                MAX(duration_seconds) as max_duration
            FROM execution_registry
            WHERE simulation_id = ?
            """,
            (simulation_id,),
        )

        row = cursor.fetchone()
        if row:
            return dict(row), 200
        return {}, 404

    def sync_pending_requests(self, installation_id):
        conn = self._get_conn()
        cursor = conn.cursor()

        if installation_id:
            cursor.execute(
                """
                SELECT * FROM sync_queue
                WHERE installation_id = ?
                AND status = 'pending'
                ORDER BY created_at
                """,
                (installation_id,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM sync_queue
                WHERE status = 'pending'
                ORDER BY created_at
                """
            )

        results = [dict(row) for row in cursor.fetchall()]
        return results, 200

    def approve_sync(self, request_id, session_id):
        import json

        if not self._check_privilege(session_id, "admin"):
            return {"error": "Admin privilege required"}, 403

        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sync_queue WHERE id = ?", (request_id,))
        # Renamed from `request` to avoid shadowing the Flask `request` global
        sync_request = cursor.fetchone()
        if not sync_request:
            return {"error": "Request not found"}, 404

        payload = json.loads(sync_request["payload"])
        result, status = self.register_simulation(payload, session_id)

        if status == 201:
            cursor.execute(
                """
                UPDATE sync_queue
                SET status = 'approved',
                    processed_at = datetime('now')
                WHERE id = ?
                """,
                (request_id,),
            )
            conn.commit()
            return {"status": "approved", "simulation_id": result["id"]}, 200
        else:
            cursor.execute(
                """
                UPDATE sync_queue
                SET status = 'failed',
                    processed_at = datetime('now'),
                    rejection_reason = ?
                WHERE id = ?
                """,
                (result.get("error", "Unknown error"), request_id),
            )
            conn.commit()
            return result, status

    def get_overview_stats(self):
        """Get overview statistics for dashboard."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM simulations")
            total_simulations = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM simulations WHERE status = 'active'")
            active_simulations = cursor.fetchone()[0]

            return {
                "total_simulations": total_simulations,
                "active_simulations": active_simulations,
                "total_executions": 0,
                "successful_executions": 0,
                "cached_executions": 0,
            }, 200
        except Exception as e:
            logger.error(f"Error getting overview stats: {e}", exc_info=True)
            return {
                "total_simulations": 0,
                "active_simulations": 0,
                "total_executions": 0,
                "successful_executions": 0,
                "cached_executions": 0,
            }, 200

    def health_check(self):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM simulations")
            count = cursor.fetchone()[0]
            return {
                "status": "healthy",
                "backend": "sqlite",
                "simulations": count,
            }, 200
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {"status": "unhealthy", "error": "Internal error"}, 500


# REST API Endpoints
@app.route("/health", methods=["GET"])
def health():
    data, status = catalog_db.health_check()
    return jsonify(data), status


@app.route("/simulations/search", methods=["GET"])
def search_simulations():
    query = request.args.get("query")
    tags = request.args.get("tags", "").split(",") if request.args.get("tags") else None
    status = request.args.get("status", "active")
    limit = request.args.get("limit", 100, type=int)

    results, status_code = catalog_db.search(query, tags, status, limit)
    return jsonify(results), status_code


@app.route("/simulations/<name>", methods=["GET"])
def get_simulation(name):
    version = request.args.get("version")
    result, status = catalog_db.get_simulation(name, version)

    if result:
        return jsonify(result), status
    return jsonify({"error": "Not found"}), status


@app.route("/simulations", methods=["POST"])
def register_simulation():
    # Read header first, then check — avoids auth bypass via default value
    session_id = request.headers.get("X-Session-ID")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401
    session_id = session_id or "no-auth-session"

    data = request.json
    result, status = catalog_db.register_simulation(data, session_id)
    return jsonify(result), status


@app.route("/simulations/<int:simulation_id>", methods=["PATCH"])
def update_simulation(simulation_id):
    # Read header first, then check — avoids auth bypass via default value
    session_id = request.headers.get("X-Session-ID")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401
    session_id = session_id or "no-auth-session"

    updates = request.json
    result, status = catalog_db.update_simulation(simulation_id, updates, session_id)
    return jsonify(result), status


@app.route("/executions", methods=["POST"])
def record_execution():
    data = request.json
    result, status = catalog_db.record_execution(data)
    return jsonify(result), status


@app.route("/simulations/<int:simulation_id>/stats", methods=["GET"])
def get_stats(simulation_id):
    result, status = catalog_db.get_stats(simulation_id)
    return jsonify(result), status


@app.route("/sync/pending", methods=["GET"])
def get_pending_sync():
    installation_id = request.args.get("installation_id")
    results, status = catalog_db.sync_pending_requests(installation_id)
    return jsonify(results), status


@app.route("/sync/<int:request_id>/approve", methods=["POST"])
def approve_sync(request_id):
    # Read header first, then check — avoids auth bypass via default value
    session_id = request.headers.get("X-Session-ID")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401
    session_id = session_id or "no-auth-session"

    result, status = catalog_db.approve_sync(request_id, session_id)
    return jsonify(result), status


@app.route("/statistics/overview", methods=["GET"])
def get_overview_stats():
    """Get overview statistics for the dashboard."""
    result, status = catalog_db.get_overview_stats()
    return jsonify(result), status


def main():
    parser = argparse.ArgumentParser(description="Sim2l Catalog Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8002, help="Port to listen on")
    parser.add_argument(
        "--backend",
        choices=["sqlite", "postgresql"],
        default="sqlite",
        help="Database backend",
    )
    parser.add_argument(
        "--db-path",
        default=str(Path.home() / ".sim2l" / "catalog.db"),
        help="SQLite database path",
    )
    parser.add_argument(
        "--db-url", help="PostgreSQL connection string (for postgresql backend)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable DEBUG logging"
    )
    parser.add_argument(
        "--no-auth", action="store_true", help="Disable authentication (for testing/development)"
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

    global catalog_db, require_auth

    if args.no_auth:
        require_auth = False
        logger.warning("Authentication DISABLED - for development/testing only!")

    if args.backend == "sqlite":
        catalog_db = SQLiteCatalogBackend(args.db_path)
        logger.info(f"Using SQLite backend: {args.db_path}")
    elif args.backend == "postgresql":
        if not args.db_url:
            logger.error("PostgreSQL backend requires --db-url")
            sys.exit(1)
        logger.error("PostgreSQL backend not yet implemented for catalog")
        sys.exit(1)

    logger.info(f"Starting catalog service on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
