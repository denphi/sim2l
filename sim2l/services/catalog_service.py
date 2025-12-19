"""
Standalone catalog service for simulation registry.

Provides REST API for tool discovery, registration, and statistics
with session-based authentication. Supports both SQLite and PostgreSQL.
"""

import os
import sys
import argparse
import logging
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
    """SQLite backend for catalog service."""

    def __init__(self, db_path: str):
        import sqlite3

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        """Create catalog database schema."""
        schema_path = (
            Path(__file__).parent.parent / "database" / "master_catalog_schema.sql"
        )

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        # Adapt PostgreSQL schema for SQLite
        schema_sql = schema_sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        schema_sql = schema_sql.replace("JSONB", "TEXT")
        schema_sql = schema_sql.replace("IF NOT EXISTS", "")
        schema_sql = schema_sql.replace("BIGINT", "INTEGER")

        # Remove PostgreSQL-specific constructs
        lines = schema_sql.split("\n")
        filtered_lines = []
        skip_block = False

        for line in lines:
            if any(x in line for x in ["CREATE OR REPLACE FUNCTION", "CREATE OR REPLACE VIEW", "CREATE TRIGGER"]):
                skip_block = True
            elif skip_block and (line.startswith("--") or line.strip() == ""):
                skip_block = False
            elif not skip_block:
                filtered_lines.append(line)

        schema_sql = "\n".join(filtered_lines)

        try:
            self.conn.executescript(schema_sql)
            self.conn.commit()
            logger.info("SQLite catalog schema created")
        except Exception as e:
            logger.error(f"Failed to create schema: {e}")

    def _check_session(self, session_id: str) -> bool:
        """Check if session is valid."""
        cursor = self.conn.cursor()
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
        import json
        cursor = self.conn.cursor()
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
        cursor = self.conn.cursor()

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
        cursor = self.conn.cursor()

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
        # Parse JSON fields
        for field in ["tags", "input_schema", "output_schema", "dependencies", "metadata"]:
            if sim.get(field):
                sim[field] = json.loads(sim[field])

        return sim, 200

    def register_simulation(self, data, session_id):
        import json

        # Check privilege
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        cursor = self.conn.cursor()

        # Get user ID from session
        cursor.execute(
            "SELECT user_id FROM sessions WHERE session_id = ?", (session_id,)
        )
        user_row = cursor.fetchone()
        user_id = user_row["user_id"] if user_row else None

        # Check if simulation already exists
        cursor.execute(
            "SELECT id FROM simulations WHERE name = ? AND version = ?",
            (data["name"], data["version"]),
        )
        if cursor.fetchone():
            return {"error": "Simulation already registered"}, 409

        # Insert simulation
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
        self.conn.commit()

        logger.info(f"Registered simulation {data['name']}/{data['version']} (ID: {simulation_id})")
        return {"id": simulation_id, "status": "registered"}, 201

    def update_simulation(self, simulation_id, updates, session_id):
        # Check privilege
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        import json
        cursor = self.conn.cursor()

        # Build update statement
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
            f"""
            UPDATE simulations
            SET {', '.join(set_clauses)}
            WHERE id = ?
            """,
            params,
        )

        self.conn.commit()
        return {"status": "updated"}, 200

    def record_execution(self, data):
        import json
        cursor = self.conn.cursor()

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

        self.conn.commit()
        return {"status": "recorded"}, 201

    def get_stats(self, simulation_id):
        cursor = self.conn.cursor()

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
        cursor = self.conn.cursor()

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

        # Check admin privilege
        if not self._check_privilege(session_id, "admin"):
            return {"error": "Admin privilege required"}, 403

        cursor = self.conn.cursor()

        # Get sync request
        cursor.execute(
            "SELECT * FROM sync_queue WHERE id = ?", (request_id,)
        )
        request = cursor.fetchone()
        if not request:
            return {"error": "Request not found"}, 404

        # Register the simulation
        payload = json.loads(request["payload"])
        result, status = self.register_simulation(payload, session_id)

        if status == 201:
            # Mark as approved
            cursor.execute(
                """
                UPDATE sync_queue
                SET status = 'approved',
                    processed_at = datetime('now')
                WHERE id = ?
                """,
                (request_id,),
            )
            self.conn.commit()
            return {"status": "approved", "simulation_id": result["id"]}, 200
        else:
            # Mark as failed
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
            self.conn.commit()
            return result, status

    def get_overview_stats(self):
        """Get overview statistics for dashboard"""
        try:
            cursor = self.conn.cursor()

            # Total simulations
            cursor.execute("SELECT COUNT(*) FROM simulations")
            total_simulations = cursor.fetchone()[0]

            # Active simulations (status = 'active')
            cursor.execute("SELECT COUNT(*) FROM simulations WHERE status = 'active'")
            active_simulations = cursor.fetchone()[0]

            # Total executions
            cursor.execute("SELECT COUNT(*) FROM executions")
            total_executions = cursor.fetchone()[0]

            # Successful executions
            cursor.execute("SELECT COUNT(*) FROM executions WHERE status = 'success'")
            successful_executions = cursor.fetchone()[0]

            # Cached executions
            cursor.execute("SELECT COUNT(*) FROM executions WHERE cache_hit = 1")
            cached_executions = cursor.fetchone()[0]

            return {
                "total_simulations": total_simulations,
                "active_simulations": active_simulations,
                "total_executions": total_executions,
                "successful_executions": successful_executions,
                "cached_executions": cached_executions,
            }, 200
        except Exception as e:
            logger.error(f"Error getting overview stats: {e}")
            return {
                "total_simulations": 0,
                "active_simulations": 0,
                "total_executions": 0,
                "successful_executions": 0,
                "cached_executions": 0,
            }, 200

    def health_check(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM simulations")
            count = cursor.fetchone()[0]
            return {
                "status": "healthy",
                "backend": "sqlite",
                "simulations": count
            }, 200
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}, 500


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
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return jsonify({"error": "Missing session ID"}), 401

    data = request.json
    result, status = catalog_db.register_simulation(data, session_id)
    return jsonify(result), status


@app.route("/simulations/<int:simulation_id>", methods=["PATCH"])
def update_simulation(simulation_id):
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return jsonify({"error": "Missing session ID"}), 401

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
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return jsonify({"error": "Missing session ID"}), 401

    result, status = catalog_db.approve_sync(request_id, session_id)
    return jsonify(result), status


@app.route("/statistics/overview", methods=["GET"])
def get_overview_stats():
    """Get overview statistics for the dashboard"""
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

    global catalog_db

    # Initialize backend
    if args.backend == "sqlite":
        catalog_db = SQLiteCatalogBackend(args.db_path)
        logger.info(f"Using SQLite backend: {args.db_path}")
    elif args.backend == "postgresql":
        if not args.db_url:
            logger.error("PostgreSQL backend requires --db-url")
            sys.exit(1)
        # PostgreSQL backend would be implemented similarly
        logger.error("PostgreSQL backend not yet implemented for catalog")
        sys.exit(1)

    # Start server
    logger.info(f"Starting catalog service on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
