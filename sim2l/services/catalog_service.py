# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

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
import json
import base64
import binascii
import hashlib
import tempfile
import time
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify
from datetime import datetime, timezone

# Shared service helpers (see sim2l/services/_common.py).
from sim2l.services._common import (
    adapt_postgres_schema_for_sqlite as _adapt_postgres_schema_for_sqlite,
    extract_session_id as _extract_session_id,
    utcnow as _utcnow,
)
import sim2l
from sim2l.definition import SimulationDefinition
from sim2l.schema import InputSchema, OutputSchema
from sim2l.executor import IsolatedFunctionExecutor, LocalExecutor, NotebookExecutor
from sim2l.database.results_client import ResultsClient

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
    """Catalog-service-specific adapter for PostgreSQL → SQLite schema SQL.

    Delegates to the shared helper with catalog-specific options: also strip
    triggers, rewrite the ``USING GIN(tags)`` index, and restore
    ``IF NOT EXISTS`` on every CREATE TABLE.
    """
    return _adapt_postgres_schema_for_sqlite(
        schema_sql,
        pg_block_starters=(
            "CREATE OR REPLACE FUNCTION",
            "CREATE OR REPLACE VIEW",
            "CREATE TRIGGER",
        ),
        extra_regex_substitutions=(
            (
                r"CREATE INDEX IF NOT EXISTS idx_simulations_tags ON simulations USING GIN\(tags\);",
                "CREATE INDEX IF NOT EXISTS idx_simulations_tags ON simulations(tags);",
            ),
        ),
        restore_if_not_exists_prefix="",  # restore on every CREATE TABLE
    )


def _default_workflow_entrypoint(workflow_type: Optional[str]) -> str:
    workflow_type = (workflow_type or "").lower()
    if workflow_type == "notebook":
        return "workflow.ipynb"
    if workflow_type in ("function", "python"):
        return "workflow.py"
    if workflow_type == "docker":
        return "Dockerfile"
    return "workflow.bin"


def _normalize_workflow_file(file_data: dict, index: int) -> dict:
    if not isinstance(file_data, dict):
        raise ValueError(f"workflow_files[{index}] must be an object")

    path = file_data.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"workflow_files[{index}].path must be a non-empty string")

    content_base64 = file_data.get("content_base64")
    if content_base64 is None:
        content = file_data.get("content")
        if content is None:
            raise ValueError(
                f"workflow_files[{index}] must contain either 'content_base64' or 'content'"
            )
        if not isinstance(content, str):
            raise ValueError(f"workflow_files[{index}].content must be a string")
        raw_content = content.encode("utf-8")
        content_base64 = base64.b64encode(raw_content).decode("ascii")
    elif not isinstance(content_base64, str):
        raise ValueError(f"workflow_files[{index}].content_base64 must be a string")
    else:
        try:
            raw_content = base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError(
                f"workflow_files[{index}].content_base64 is not valid base64"
            )

    normalized = {
        "path": path,
        "encoding": "base64",
        "content_base64": content_base64,
        "size_bytes": len(raw_content),
        "sha256": hashlib.sha256(raw_content).hexdigest(),
    }

    for optional_key in ("content_type", "mode", "description"):
        value = file_data.get(optional_key)
        if value is not None:
            normalized[optional_key] = value

    return normalized


def _normalize_workflow_bundle(payload: dict) -> Optional[dict]:
    workflow_type = payload.get("workflow_type", "notebook")
    workflow_entrypoint = payload.get("workflow_entrypoint")

    bundle = payload.get("workflow_bundle")
    if bundle is not None:
        if isinstance(bundle, str):
            try:
                bundle = json.loads(bundle)
            except Exception:
                raise ValueError("workflow_bundle must be valid JSON")
        if not isinstance(bundle, dict):
            raise ValueError("workflow_bundle must be an object")

        raw_files = bundle.get("files", [])
        if not isinstance(raw_files, list):
            raise ValueError("workflow_bundle.files must be a list")

        normalized_files = []
        seen_paths = set()
        for i, file_data in enumerate(raw_files):
            normalized = _normalize_workflow_file(file_data, i)
            if normalized["path"] in seen_paths:
                raise ValueError(f"workflow_bundle.files has duplicate path '{normalized['path']}'")
            seen_paths.add(normalized["path"])
            normalized_files.append(normalized)

        normalized_bundle = dict(bundle)
        normalized_bundle["format_version"] = bundle.get("format_version", 1)
        normalized_bundle["workflow_type"] = bundle.get("workflow_type", workflow_type)
        normalized_bundle["entrypoint"] = (
            bundle.get("entrypoint")
            or workflow_entrypoint
            or _default_workflow_entrypoint(normalized_bundle["workflow_type"])
        )
        normalized_bundle["files"] = normalized_files
        return normalized_bundle

    workflow_files = payload.get("workflow_files")
    if workflow_files is None:
        workflow_files = []
        workflow_data_base64 = payload.get("workflow_data_base64")
        workflow_data = payload.get("workflow_data")
        dockerfile = payload.get("dockerfile")
        docker_context_files = payload.get("docker_context_files")

        if workflow_data_base64 is not None:
            workflow_files.append(
                {
                    "path": workflow_entrypoint or _default_workflow_entrypoint(workflow_type),
                    "content_base64": workflow_data_base64,
                }
            )
        elif workflow_data is not None:
            workflow_files.append(
                {
                    "path": workflow_entrypoint or _default_workflow_entrypoint(workflow_type),
                    "content": workflow_data,
                }
            )

        if dockerfile is not None:
            workflow_files.append(
                {
                    "path": "Dockerfile",
                    "content": dockerfile,
                    "content_type": "text/plain",
                }
            )

        if docker_context_files is not None:
            if not isinstance(docker_context_files, list):
                raise ValueError("docker_context_files must be a list")
            workflow_files.extend(docker_context_files)

        if not workflow_files:
            return None

    if not isinstance(workflow_files, list):
        raise ValueError("workflow_files must be a list")

    normalized_files = []
    seen_paths = set()
    for i, file_data in enumerate(workflow_files):
        normalized = _normalize_workflow_file(file_data, i)
        if normalized["path"] in seen_paths:
            raise ValueError(f"workflow_files has duplicate path '{normalized['path']}'")
        seen_paths.add(normalized["path"])
        normalized_files.append(normalized)

    return {
        "format_version": 1,
        "workflow_type": workflow_type,
        "entrypoint": workflow_entrypoint or _default_workflow_entrypoint(workflow_type),
        "files": normalized_files,
    }


def _normalize_schema(schema_value, field_name: str) -> Optional[dict]:
    if schema_value is None:
        return None
    if isinstance(schema_value, str):
        try:
            schema_value = json.loads(schema_value)
        except Exception:
            raise ValueError(f"{field_name} must be valid JSON")
    if not isinstance(schema_value, dict):
        raise ValueError(f"{field_name} must be an object")
    return schema_value


def _resolve_input_output_schemas(payload: dict, workflow_bundle: Optional[dict]) -> tuple[dict, dict]:
    input_schema = payload.get("input_schema")
    output_schema = payload.get("output_schema")

    if workflow_bundle:
        if input_schema is None:
            input_schema = workflow_bundle.get("input_schema")
        if output_schema is None:
            output_schema = workflow_bundle.get("output_schema")

        schemas = workflow_bundle.get("schemas")
        if isinstance(schemas, dict):
            if input_schema is None:
                input_schema = schemas.get("input")
            if output_schema is None:
                output_schema = schemas.get("output")

    input_schema = _normalize_schema(input_schema, "input_schema")
    output_schema = _normalize_schema(output_schema, "output_schema")

    if input_schema is None or output_schema is None:
        raise ValueError(
            "input_schema and output_schema are required "
            "(provide directly or include them in workflow_bundle)"
        )

    return input_schema, output_schema


def _file_content_from_bundle(workflow_bundle: dict, entrypoint: str) -> bytes:
    for file_data in workflow_bundle.get("files", []):
        if file_data.get("path") != entrypoint:
            continue
        if file_data.get("encoding") == "base64":
            return base64.b64decode(file_data.get("content_base64", ""))
        content = file_data.get("content")
        if content is not None:
            return str(content).encode("utf-8")
    raise ValueError(f"Workflow entrypoint '{entrypoint}' not found in workflow_bundle")


def _workflow_hash_from_bundle(workflow_bundle: Optional[dict]) -> Optional[str]:
    if not workflow_bundle:
        return None
    digest = hashlib.sha256()
    for file_data in sorted(workflow_bundle.get("files", []), key=lambda item: item.get("path", "")):
        digest.update(str(file_data.get("path", "")).encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_content_from_bundle(workflow_bundle, file_data.get("path", "")))
        digest.update(b"\0")
    return digest.hexdigest()


def _simulation_from_catalog_record(record: dict) -> SimulationDefinition:
    workflow_bundle = record.get("workflow_bundle")
    if not workflow_bundle:
        raise ValueError(
            "Simulation has no workflow_bundle; deploy it locally or re-register with workflow files"
        )

    workflow_type = (workflow_bundle.get("workflow_type") or record.get("workflow_type") or "notebook").lower()
    entrypoint = workflow_bundle.get("entrypoint") or _default_workflow_entrypoint(workflow_type)
    workflow_bytes = _file_content_from_bundle(workflow_bundle, entrypoint)

    if workflow_type in {"function", "python"}:
        workflow = workflow_bytes
        workflow_type = "function"
    elif workflow_type == "notebook":
        tmp = tempfile.NamedTemporaryFile(prefix="sim2l_catalog_", suffix=".ipynb", delete=False)
        try:
            tmp.write(workflow_bytes)
            tmp.close()
            workflow = Path(tmp.name)
        except Exception:
            tmp.close()
            raise
    else:
        raise ValueError(f"Unsupported catalog workflow_type for /run: {workflow_type}")

    return SimulationDefinition(
        name=record["name"],
        version=record["version"],
        inputs=InputSchema.from_dict(record.get("input_schema") or {}),
        outputs=OutputSchema.from_dict(record.get("output_schema") or {}),
        workflow=workflow,
        description=record.get("description") or "",
        author=record.get("author") or "",
        tags=record.get("tags") or [],
        dependencies=record.get("dependencies") or [],
        workflow_type=workflow_type,
    )


def _register_service_result(result, params: dict, outputs: dict, session_id: Optional[str]) -> None:
    """Mirror a catalog-service run to the configured results service."""
    config = sim2l.get_config()
    if not config.results_service_url:
        return

    client = ResultsClient(
        config.results_service_url,
        session_id=config.results_session_id or session_id,
    )
    client.register_direct(
        execution_id=result.execution_id,
        simulation_name=result.simulation_name,
        simulation_version=result.simulation_version,
        squid_id=result.squid_id,
        input_params=params,
        output_params=outputs if isinstance(outputs, dict) else {},
        status=result.status,
        duration_seconds=result.duration_seconds,
        run_db_path="",
        metadata={"source": "catalog_service.run"},
    )


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

    def delete_simulation(self, simulation_id, session_id):
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

    def can_run_simulation(self, session_id: str):
        raise NotImplementedError

    def refresh_session(self, session_id: str):
        raise NotImplementedError

    def health_check(self):
        raise NotImplementedError


class SQLiteCatalogBackend(CatalogServiceBackend):
    """SQLite backend for catalog service.

    Uses a per-thread connection pool (threading.local) so that concurrent
    Flask requests each get their own SQLite connection, avoiding
    'OperationalError: database is locked' errors under load.
    WAL journal mode is enabled for better read concurrency.

    The ``no_auth`` flag is set once at startup. When True (and only when
    True), session_id "no-auth-session" auto-grants all privileges. This is
    a *server*-side flag — it cannot be triggered by anything a client sends.
    """

    def __init__(self, db_path: str, no_auth: bool = False):
        self.db_path = db_path
        self.no_auth = no_auth
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
                self._ensure_schema_extensions(conn)
                conn.commit()
                logger.info("SQLite catalog schema created")
            except Exception as e:
                logger.error(f"Failed to create schema: {e}")

    def _ensure_schema_extensions(self, conn):
        """Apply non-breaking schema upgrades for existing SQLite databases."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(simulations)")
        columns = {row["name"] for row in cursor.fetchall()}

        if "workflow_bundle" not in columns:
            cursor.execute("ALTER TABLE simulations ADD COLUMN workflow_bundle TEXT")
            logger.info("Added 'workflow_bundle' column to SQLite catalog schema")

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
        """Check if session has privilege.

        Only honors the "no-auth-session" sentinel when the backend was
        constructed with ``no_auth=True``. In production (auth enabled) the
        sentinel is ignored — even if a client sends it as ``X-Session-ID``.
        """
        if self.no_auth and session_id == "no-auth-session":
            return True

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

    def can_run_simulation(self, session_id: str):
        if not self._check_session(session_id):
            return {"error": "Invalid or expired session"}, 401
        for privilege in ("execute", "run"):
            if self._check_privilege(session_id, privilege):
                return {"allowed": True}, 200
        return {"error": "Insufficient privileges"}, 403

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
                   created_at, updated_at, input_schema, output_schema
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
            sim["input_schema"] = json.loads(sim["input_schema"]) if sim.get("input_schema") else {}
            sim["output_schema"] = json.loads(sim["output_schema"]) if sim.get("output_schema") else {}

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
        for field in [
            "tags",
            "input_schema",
            "output_schema",
            "dependencies",
            "metadata",
            "workflow_bundle",
        ]:
            if sim.get(field):
                sim[field] = json.loads(sim[field])

        return sim, 200

    def register_simulation(self, data, session_id):
        import json

        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        try:
            workflow_bundle = _normalize_workflow_bundle(data)
            input_schema, output_schema = _resolve_input_output_schemas(
                data, workflow_bundle
            )
        except ValueError as exc:
            return {"error": str(exc)}, 400

        conn = self._get_conn()
        cursor = conn.cursor()

        if self.no_auth and session_id == "no-auth-session":
            user_id = None
        else:
            cursor.execute(
                "SELECT user_id FROM sessions WHERE session_id = ?", (session_id,)
            )
            user_row = cursor.fetchone()
            user_id = user_row["user_id"] if user_row else None

        # Use INSERT OR IGNORE inside an IMMEDIATE transaction so concurrent
        # registers cannot both pass a pre-INSERT SELECT and then collide on
        # the UNIQUE constraint with a 500. If the insert is ignored, the row
        # already existed → return a clean 409.
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO simulations (
                    name, version, description, author, author_email,
                    organization, license, repository_url, documentation_url,
                    tags, input_schema, output_schema, workflow_type,
                    workflow_hash, workflow_bundle, dependencies, python_version, status,
                    visibility, created_by, updated_by, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(input_schema),
                    json.dumps(output_schema),
                    data.get("workflow_type", "notebook"),
                    data.get("workflow_hash") or _workflow_hash_from_bundle(workflow_bundle),
                    json.dumps(workflow_bundle) if workflow_bundle is not None else None,
                    json.dumps(data.get("dependencies", [])),
                    data.get("python_version"),
                    "active",
                    data.get("visibility", "public"),
                    user_id,
                    user_id,
                    json.dumps(data.get("metadata")),
                ),
            )

            if cursor.rowcount == 0:
                # Row was ignored → another transaction already inserted it.
                conn.commit()
                return {"error": "Simulation already registered"}, 409

            simulation_id = cursor.lastrowid
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        logger.info(f"Registered simulation {data['name']}/{data['version']} (ID: {simulation_id})")
        return {"id": simulation_id, "status": "registered"}, 201

    def update_simulation(self, simulation_id, updates, session_id):
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        normalized_updates = dict(updates)
        if any(
            key in updates
            for key in (
                "workflow_bundle",
                "workflow_files",
                "workflow_entrypoint",
                "workflow_data",
                "workflow_data_base64",
                "dockerfile",
                "docker_context_files",
            )
        ):
            payload = {"workflow_type": updates.get("workflow_type", "notebook"), **updates}
            try:
                normalized_updates["workflow_bundle"] = _normalize_workflow_bundle(payload)
            except ValueError as exc:
                return {"error": str(exc)}, 400

        set_clauses = []
        params = []

        for key, value in normalized_updates.items():
            if key in [
                "tags",
                "dependencies",
                "metadata",
                "input_schema",
                "output_schema",
                "workflow_bundle",
            ]:
                set_clauses.append(f"{key} = ?")
                params.append(json.dumps(value))
            elif key in [
                "description",
                "status",
                "visibility",
                "license",
                "workflow_type",
                "workflow_hash",
            ]:
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

    def delete_simulation(self, simulation_id, session_id):
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, name, version FROM simulations WHERE id = ?",
            (simulation_id,),
        )
        simulation = cursor.fetchone()
        if not simulation:
            return {"error": "Simulation not found"}, 404

        # execution_registry does not cascade on simulation delete in this schema.
        cleanup_statements = [
            ("DELETE FROM execution_registry WHERE simulation_id = ?", (simulation_id,)),
            ("DELETE FROM execution_stats WHERE simulation_id = ?", (simulation_id,)),
            ("DELETE FROM simulation_tags WHERE simulation_id = ?", (simulation_id,)),
            ("DELETE FROM access_control WHERE simulation_id = ?", (simulation_id,)),
            (
                "DELETE FROM simulation_dependencies WHERE simulation_id = ? OR depends_on_simulation_id = ?",
                (simulation_id, simulation_id),
            ),
        ]
        for statement, params in cleanup_statements:
            try:
                cursor.execute(statement, params)
            except Exception as exc:
                # Backward compatibility for older SQLite DBs that may miss optional tables.
                if "no such table" in str(exc).lower():
                    logger.debug(f"Skipping cleanup statement due to missing table: {statement}")
                else:
                    raise

        cursor.execute("DELETE FROM simulations WHERE id = ?", (simulation_id,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count == 0:
            return {"error": "Simulation not found"}, 404

        logger.info(
            f"Deleted simulation {simulation['name']}/{simulation['version']} (ID: {simulation_id})"
        )
        return {
            "status": "deleted",
            "simulation_id": simulation_id,
            "name": simulation["name"],
            "version": simulation["version"],
        }, 200

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

    def refresh_session(self, session_id: str):
        """Extend session TTL by 24 hours."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sessions
            SET expires_at = datetime(expires_at, '+24 hours')
            WHERE session_id = ?
              AND is_valid = 1
              AND expires_at > datetime('now')
            """,
            (session_id,),
        )
        if cursor.rowcount == 0:
            conn.commit()
            return {"error": "Session not found or already expired"}, 404
        conn.commit()
        cursor.execute(
            "SELECT expires_at FROM sessions WHERE session_id = ?", (session_id,)
        )
        row = cursor.fetchone()
        return {"session_id": session_id, "expires_at": row[0] if row else None}, 200

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


class PostgreSQLCatalogBackend(CatalogServiceBackend):
    """PostgreSQL backend for catalog service.

    Uses a per-thread connection pool (threading.local) for thread safety
    under concurrent Flask requests.

    The ``no_auth`` flag is set once at startup. When True (and only when
    True), session_id "no-auth-session" auto-grants all privileges. This is
    a *server*-side flag — it cannot be triggered by anything a client sends.
    """

    def __init__(self, connection_string: str, no_auth: bool = False):
        self.connection_string = connection_string
        self.no_auth = no_auth
        self._local = threading.local()
        self._create_schema()

    def _get_conn(self):
        """Return the per-thread PostgreSQL connection, creating it if needed."""
        import psycopg2
        import psycopg2.extras

        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed:
            conn = psycopg2.connect(
                self.connection_string,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            self._local.conn = conn
        return conn

    def _create_schema(self):
        """Create catalog schema if needed.

        The PostgreSQL schema file contains some non-idempotent statements
        (e.g., trigger creation). To avoid duplicate-object failures on
        service restart, only apply the schema on first initialization.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT to_regclass('public.simulations') AS simulations_table")
        row = cursor.fetchone() or {}
        if row.get("simulations_table"):
            logger.debug("PostgreSQL catalog schema already initialized")
        else:
            schema_path = Path(__file__).parent.parent / "database" / "master_catalog_schema.sql"
            with open(schema_path, "r") as f:
                schema_sql = f.read()

            cursor.execute(schema_sql)
            conn.commit()
            logger.info("PostgreSQL catalog schema created")

        self._ensure_schema_extensions()

    def _ensure_schema_extensions(self):
        """Apply non-breaking schema upgrades for existing PostgreSQL databases."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            ALTER TABLE simulations
            ADD COLUMN IF NOT EXISTS workflow_bundle JSONB
            """
        )
        conn.commit()

    def _check_session(self, session_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM sessions
            WHERE session_id = %s
            AND is_valid = true
            AND expires_at > CURRENT_TIMESTAMP
            """,
            (session_id,),
        )
        return cursor.fetchone() is not None

    def _check_privilege(self, session_id: str, privilege: str) -> bool:
        """Check if session has privilege.

        Only honors the "no-auth-session" sentinel when the backend was
        constructed with ``no_auth=True``. In production (auth enabled) the
        sentinel is ignored — even if a client sends it as ``X-Session-ID``.
        """
        if self.no_auth and session_id == "no-auth-session":
            return True

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT privileges FROM sessions
            WHERE session_id = %s
            AND is_valid = true
            AND expires_at > CURRENT_TIMESTAMP
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False

        privileges = row.get("privileges") or []
        if isinstance(privileges, str):
            try:
                privileges = json.loads(privileges)
            except Exception:
                privileges = []

        return privilege in privileges or "admin" in privileges

    def can_run_simulation(self, session_id: str):
        if not self._check_session(session_id):
            return {"error": "Invalid or expired session"}, 401
        for privilege in ("execute", "run"):
            if self._check_privilege(session_id, privilege):
                return {"allowed": True}, 200
        return {"error": "Insufficient privileges"}, 403

    def _normalize_json(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    def search(self, query, tags, status, limit):
        conn = self._get_conn()
        cursor = conn.cursor()

        conditions = []
        params = []

        if query:
            conditions.append("name ILIKE %s")
            params.append(f"%{query}%")

        if status and status != "all":
            conditions.append("status = %s")
            params.append(status)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(
            f"""
            SELECT id, name, version, description, author, tags, status,
                   created_at, updated_at, input_schema, output_schema
            FROM simulations
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params + [limit],
        )

        results = []
        for row in cursor.fetchall():
            sim = dict(row)
            sim["tags"] = self._normalize_json(sim.get("tags")) or []
            sim["input_schema"] = self._normalize_json(sim.get("input_schema")) or {}
            sim["output_schema"] = self._normalize_json(sim.get("output_schema")) or {}

            # Filter by tags if specified
            if tags:
                sim_tags = set(sim["tags"]) if isinstance(sim["tags"], list) else set()
                if not sim_tags.intersection(set(tags)):
                    continue

            if sim.get("created_at"):
                sim["created_at"] = str(sim["created_at"])
            if sim.get("updated_at"):
                sim["updated_at"] = str(sim["updated_at"])

            results.append(sim)

        return results, 200

    def get_simulation(self, name, version):
        conn = self._get_conn()
        cursor = conn.cursor()

        if version:
            cursor.execute(
                """
                SELECT * FROM simulations
                WHERE name = %s AND version = %s
                """,
                (name, version),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM simulations
                WHERE name = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (name,),
            )

        row = cursor.fetchone()
        if not row:
            return None, 404

        sim = dict(row)
        for field in [
            "tags",
            "input_schema",
            "output_schema",
            "dependencies",
            "metadata",
            "workflow_bundle",
        ]:
            sim[field] = self._normalize_json(sim.get(field))

        if sim.get("created_at"):
            sim["created_at"] = str(sim["created_at"])
        if sim.get("updated_at"):
            sim["updated_at"] = str(sim["updated_at"])

        return sim, 200

    def register_simulation(self, data, session_id):
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        try:
            workflow_bundle = _normalize_workflow_bundle(data)
            input_schema, output_schema = _resolve_input_output_schemas(
                data, workflow_bundle
            )
        except ValueError as exc:
            return {"error": str(exc)}, 400

        conn = self._get_conn()
        cursor = conn.cursor()

        if self.no_auth and session_id == "no-auth-session":
            user_id = None
        else:
            cursor.execute(
                "SELECT user_id FROM sessions WHERE session_id = %s", (session_id,)
            )
            user_row = cursor.fetchone()
            user_id = user_row["user_id"] if user_row else None

        # Use ON CONFLICT DO NOTHING + RETURNING so concurrent inserts cannot
        # both pass a pre-INSERT SELECT and then collide on the UNIQUE
        # constraint with a 500. If RETURNING yields no row, the conflict
        # fired → return a clean 409.
        try:
            cursor.execute(
                """
                INSERT INTO simulations (
                    name, version, description, author, author_email,
                    organization, license, repository_url, documentation_url,
                    tags, input_schema, output_schema, workflow_type,
                    workflow_hash, workflow_bundle, dependencies, python_version, status,
                    visibility, created_by, updated_by, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                          %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (name, version) DO NOTHING
                RETURNING id
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
                    json.dumps(input_schema),
                    json.dumps(output_schema),
                    data.get("workflow_type", "notebook"),
                    data.get("workflow_hash") or _workflow_hash_from_bundle(workflow_bundle),
                    json.dumps(workflow_bundle) if workflow_bundle is not None else None,
                    json.dumps(data.get("dependencies", [])),
                    data.get("python_version"),
                    "active",
                    data.get("visibility", "public"),
                    user_id,
                    user_id,
                    json.dumps(data.get("metadata")),
                ),
            )

            row = cursor.fetchone()
            if row is None:
                conn.commit()
                return {"error": "Simulation already registered"}, 409

            simulation_id = row["id"]
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        logger.info(f"Registered simulation {data['name']}/{data['version']} (ID: {simulation_id})")
        return {"id": simulation_id, "status": "registered"}, 201

    def update_simulation(self, simulation_id, updates, session_id):
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        normalized_updates = dict(updates)
        if any(
            key in updates
            for key in (
                "workflow_bundle",
                "workflow_files",
                "workflow_entrypoint",
                "workflow_data",
                "workflow_data_base64",
                "dockerfile",
                "docker_context_files",
            )
        ):
            payload = {"workflow_type": updates.get("workflow_type", "notebook"), **updates}
            try:
                normalized_updates["workflow_bundle"] = _normalize_workflow_bundle(payload)
            except ValueError as exc:
                return {"error": str(exc)}, 400

        set_clauses = []
        params = []

        for key, value in normalized_updates.items():
            if key in [
                "tags",
                "dependencies",
                "metadata",
                "input_schema",
                "output_schema",
                "workflow_bundle",
            ]:
                set_clauses.append(f"{key} = %s::jsonb")
                params.append(json.dumps(value))
            elif key in [
                "description",
                "status",
                "visibility",
                "license",
                "workflow_type",
                "workflow_hash",
            ]:
                set_clauses.append(f"{key} = %s")
                params.append(value)

        if not set_clauses:
            return {"error": "No valid fields to update"}, 400

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(simulation_id)

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE simulations SET {', '.join(set_clauses)} WHERE id = %s",
            params,
        )
        conn.commit()

        return {"status": "updated"}, 200

    def delete_simulation(self, simulation_id, session_id):
        if not self._check_privilege(session_id, "catalog_update"):
            return {"error": "Insufficient privileges"}, 403

        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, name, version FROM simulations WHERE id = %s",
            (simulation_id,),
        )
        simulation = cursor.fetchone()
        if not simulation:
            return {"error": "Simulation not found"}, 404

        cursor.execute("DELETE FROM execution_registry WHERE simulation_id = %s", (simulation_id,))
        cursor.execute("DELETE FROM execution_stats WHERE simulation_id = %s", (simulation_id,))
        cursor.execute("DELETE FROM simulation_tags WHERE simulation_id = %s", (simulation_id,))
        cursor.execute("DELETE FROM access_control WHERE simulation_id = %s", (simulation_id,))
        cursor.execute(
            "DELETE FROM simulation_dependencies WHERE simulation_id = %s OR depends_on_simulation_id = %s",
            (simulation_id, simulation_id),
        )
        cursor.execute("DELETE FROM simulations WHERE id = %s", (simulation_id,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count == 0:
            return {"error": "Simulation not found"}, 404

        logger.info(
            f"Deleted simulation {simulation['name']}/{simulation['version']} (ID: {simulation_id})"
        )
        return {
            "status": "deleted",
            "simulation_id": simulation_id,
            "name": simulation["name"],
            "version": simulation["version"],
        }, 200

    def record_execution(self, data):
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
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
                SUM(CASE WHEN cache_hit = true THEN 1 ELSE 0 END) as cached,
                AVG(duration_seconds) as avg_duration,
                MIN(duration_seconds) as min_duration,
                MAX(duration_seconds) as max_duration
            FROM execution_registry
            WHERE simulation_id = %s
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
                WHERE installation_id = %s
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
        if not self._check_privilege(session_id, "admin"):
            return {"error": "Admin privilege required"}, 403

        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sync_queue WHERE id = %s", (request_id,))
        sync_request = cursor.fetchone()
        if not sync_request:
            return {"error": "Request not found"}, 404

        payload = self._normalize_json(sync_request.get("payload")) or {}
        result, status = self.register_simulation(payload, session_id)

        if status == 201:
            cursor.execute(
                """
                UPDATE sync_queue
                SET status = 'approved',
                    processed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (request_id,),
            )
            conn.commit()
            return {"status": "approved", "simulation_id": result["id"]}, 200

        cursor.execute(
            """
            UPDATE sync_queue
            SET status = 'failed',
                processed_at = CURRENT_TIMESTAMP,
                rejection_reason = %s
            WHERE id = %s
            """,
            (result.get("error", "Unknown error"), request_id),
        )
        conn.commit()
        return result, status

    def get_overview_stats(self):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) AS count FROM simulations")
            total_simulations = (cursor.fetchone() or {}).get("count", 0)

            cursor.execute("SELECT COUNT(*) AS count FROM simulations WHERE status = 'active'")
            active_simulations = (cursor.fetchone() or {}).get("count", 0)

            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_executions,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_executions,
                    SUM(CASE WHEN cache_hit = true THEN 1 ELSE 0 END) as cached_executions
                FROM execution_registry
                """
            )
            exec_stats = cursor.fetchone() or {}

            return {
                "total_simulations": total_simulations or 0,
                "active_simulations": active_simulations or 0,
                "total_executions": exec_stats.get("total_executions", 0) or 0,
                "successful_executions": exec_stats.get("successful_executions", 0) or 0,
                "cached_executions": exec_stats.get("cached_executions", 0) or 0,
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

    def refresh_session(self, session_id: str):
        """Extend session TTL by 24 hours."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE sessions
            SET expires_at = expires_at + INTERVAL '24 hours'
            WHERE session_id = %s
              AND is_valid = true
              AND expires_at > CURRENT_TIMESTAMP
            RETURNING expires_at
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            conn.rollback()
            return {"error": "Session not found or already expired"}, 404
        conn.commit()
        expires_at = row.get("expires_at") if isinstance(row, dict) else row[0]
        return {"session_id": session_id, "expires_at": str(expires_at)}, 200

    def health_check(self):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS count FROM simulations")
            row = cursor.fetchone() or {}
            count = row.get("count", 0) or 0
            return {
                "status": "healthy",
                "backend": "postgresql",
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


@app.route("/session/refresh", methods=["POST"])
def refresh_session():
    """Extend the expiry of the current session by the default TTL."""
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return jsonify({"error": "Missing session ID"}), 401

    result, status_code = catalog_db.refresh_session(session_id)
    return jsonify(result), status_code


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
    if require_auth:
        if not session_id:
            return jsonify({"error": "Missing session ID"}), 401
    else:
        # In no-auth mode, always use elevated local session regardless of header value.
        session_id = "no-auth-session"

    data = request.json
    result, status = catalog_db.register_simulation(data, session_id)
    return jsonify(result), status


@app.route("/simulations/<int:simulation_id>", methods=["PATCH"])
def update_simulation(simulation_id):
    session_id = request.headers.get("X-Session-ID")
    if require_auth:
        if not session_id:
            return jsonify({"error": "Missing session ID"}), 401
    else:
        # In no-auth mode, always use elevated local session regardless of header value.
        session_id = "no-auth-session"

    updates = request.json
    result, status = catalog_db.update_simulation(simulation_id, updates, session_id)
    return jsonify(result), status


@app.route("/simulations/<int:simulation_id>", methods=["DELETE"])
def delete_simulation(simulation_id):
    session_id = request.headers.get("X-Session-ID")
    if require_auth:
        if not session_id:
            return jsonify({"error": "Missing session ID"}), 401
    else:
        # In no-auth mode, always use elevated local session regardless of header value.
        session_id = "no-auth-session"

    result, status = catalog_db.delete_simulation(simulation_id, session_id)
    return jsonify(result), status


@app.route("/simulations", methods=["DELETE"])
def clear_all_simulations():
    session_id = request.headers.get("X-Session-ID")
    if require_auth:
        if not session_id:
            return jsonify({"error": "Missing session ID"}), 401
    else:
        session_id = "no-auth-session"

    try:
        sims, search_status = catalog_db.search(query=None, tags=None, status="all", limit=10000)
        if search_status != 200:
            return jsonify({"error": "Could not list simulations"}), search_status
        deleted = 0
        for sim in sims:
            _, status = catalog_db.delete_simulation(sim["id"], session_id)
            if status == 200:
                deleted += 1
        return jsonify({"deleted": deleted}), 200
    except Exception as exc:
        logger.error(f"Clear all simulations failed: {exc}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/executions", methods=["POST"])
def record_execution():
    session_id = request.headers.get("X-Session-ID")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401
    if require_auth:
        auth_result, auth_status = catalog_db.can_run_simulation(session_id)
        if auth_status != 200:
            return jsonify(auth_result), auth_status

    data = request.json
    result, status = catalog_db.record_execution(data)
    return jsonify(result), status


@app.route("/run", methods=["POST"])
def run_simulation():
    """Run a simulation and return the execution results."""
    # Read header first, then check — avoids auth bypass via default value
    session_id = request.headers.get("X-Session-ID")
    if require_auth and not session_id:
        return jsonify({"error": "Missing session ID"}), 401
    if require_auth:
        auth_result, auth_status = catalog_db.can_run_simulation(session_id)
        if auth_status != 200:
            return jsonify(auth_result), auth_status
    else:
        session_id = "no-auth-session"

    data = request.json
    if not data:
        return jsonify({'error': 'No JSON payload provided'}), 400

    simulation_name = data.get('simulation_name')
    version = data.get('version')
    params = data.get('params', {})

    if not simulation_name:
        return jsonify({'error': 'simulation_name is required'}), 400

    try:
        # Load the simulation from the catalog first. This makes the service
        # API authoritative for simulations registered through /simulations.
        sim_record, sim_status = catalog_db.get_simulation(simulation_name, version)
        if sim_status == 200 and sim_record:
            sim = _simulation_from_catalog_record(sim_record)
        else:
            sim = sim2l.load_simulation(simulation_name, version=version)
        
        # Use appropriate executor based on workflow type. Catalog function
        # bundles are source-backed and run in a child process so submitted
        # source never executes in the Flask worker process.
        if getattr(sim, 'workflow_type', 'python') == 'notebook':
            executor = NotebookExecutor(cache=True)
        elif getattr(sim, 'workflow_type', 'python') == 'function' and sim_status == 200:
            executor = IsolatedFunctionExecutor(cache=True, save_result=False)
        else:
            executor = LocalExecutor(cache=True)
        
        # Run simulation
        import time
        start_time = time.time()
        result = sim.run(**params, executor=executor)
        elapsed_time = time.time() - start_time
        
        # Format the output to return
        outputs = result.outputs.to_dict() if hasattr(result.outputs, 'to_dict') else result.outputs
        if hasattr(outputs, 'dict'):
            outputs = outputs.dict()
        if hasattr(outputs, '__dict__'):
            outputs = vars(outputs)

        # Use the shared serialization helper instead of an ad-hoc local
        # `make_serializable` copy — it already handles dicts/lists/np
        # arrays/np scalars/Pint quantities and stays in sync with the rest
        # of the codebase.
        from sim2l.utils.serialization import serialize_for_hashing
        outputs = serialize_for_hashing(outputs)

        if sim_status == 200 and sim_record and sim_record.get("id"):
            catalog_db.record_execution({
                "execution_id": result.execution_id,
                "squid_id": result.squid_id or result.execution_id,
                "simulation_id": sim_record["id"],
                "user_id": None,
                "started_at": datetime.fromtimestamp(start_time, tz=timezone.utc).replace(tzinfo=None).isoformat(),
                "completed_at": _utcnow().isoformat(),
                "duration_seconds": result.duration_seconds or elapsed_time,
                "status": result.status,
                "executor_type": result.executor_type,
                "cache_hit": False,
                "run_db_path": None,
                "run_db_size_bytes": None,
                "input_hash": hashlib.sha256(
                    json.dumps(params, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest(),
                "output_count": len(outputs) if isinstance(outputs, dict) else 0,
                "artifact_count": 0,
                "error_count": 1 if result.status != "completed" else 0,
                "warning_count": 0,
                "environment": {"source": "catalog_service.run"},
            })
        _register_service_result(result, params, outputs, session_id)
            
        return jsonify({
            'success': True,
            'execution_id': result.execution_id,
            'squid_id': result.squid_id,
            'status': result.status,
            'duration_seconds': result.duration_seconds or elapsed_time,
            'outputs': outputs
        })

    except ValueError as e:
        logger.error(f"Validation error running simulation {simulation_name}: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error executing simulation {simulation_name}: {e}", exc_info=True)
        return jsonify({'error': f"Execution failed: {str(e)}"}), 500


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
    if require_auth:
        if not session_id:
            return jsonify({"error": "Missing session ID"}), 401
    else:
        # In no-auth mode, always use elevated local session regardless of header value.
        session_id = "no-auth-session"

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
        catalog_db = SQLiteCatalogBackend(args.db_path, no_auth=not require_auth)
        logger.info(f"Using SQLite backend: {args.db_path}")
    elif args.backend == "postgresql":
        if not args.db_url:
            logger.error("PostgreSQL backend requires --db-url")
            sys.exit(1)
        catalog_db = PostgreSQLCatalogBackend(args.db_url, no_auth=not require_auth)
        logger.info("Using PostgreSQL backend")

    logger.info(f"Starting catalog service on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
