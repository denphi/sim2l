# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Results Service for sim2l.

This service introspects simulation results and stores them in a searchable database.
It extracts input/output parameters, their types, and values for powerful querying.

Similar to the legacy registerSquidpgSimtool but modernized for sim2l architecture.
"""

import os
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from flask import Flask, request, jsonify

from ..database.run_database import RunDatabase
from ..database.session_manager import get_session_manager, Session


logger = logging.getLogger(__name__)


# ============================================================================
# Backend Implementations
# ============================================================================

class ResultsBackend:
    """Base class for results storage backends."""

    def register_schema(
        self,
        tool_name: str,
        tool_version: str,
        schema_data: Dict[str, Any]
    ) -> int:
        """Register or update a simulation schema."""
        raise NotImplementedError

    def register_result(
        self,
        execution_id: str,
        simulation_name: str,
        simulation_version: str,
        squid_id: str,
        input_params: Dict[str, Any],
        output_params: Dict[str, Any],
        status: str,
        duration_seconds: Optional[float],
        run_db_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Register an execution result."""
        raise NotImplementedError

    def search_results(
        self,
        simulation_name: Optional[str] = None,
        input_filters: Optional[Dict[str, Any]] = None,
        output_filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search results by parameter values."""
        raise NotImplementedError

    def get_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific execution result."""
        raise NotImplementedError

    def delete_result(self, execution_id: str) -> Tuple[Dict[str, Any], int]:
        """Delete a specific execution result."""
        raise NotImplementedError

    def get_parameter_stats(
        self,
        simulation_name: str,
        param_name: str,
        param_class: str = 'output'
    ) -> Dict[str, Any]:
        """Get statistics for a parameter."""
        raise NotImplementedError

    def record_error(
        self,
        execution_id: Optional[str],
        simulation_name: str,
        simulation_version: Optional[str],
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None
    ) -> None:
        """Record an error during result registration."""
        raise NotImplementedError


class SQLiteResultsBackend(ResultsBackend):
    """SQLite implementation of results storage.

    Uses a per-thread connection pool (threading.local) so that concurrent
    Flask requests each get their own SQLite connection, avoiding
    'OperationalError: database is locked' errors under load.
    WAL journal mode is enabled for better read concurrency.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.sim2l/results.db")

        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self._local = threading.local()
        self._schema_lock = threading.Lock()
        self._initialize_schema()

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

    def _initialize_schema(self):
        """Initialize SQLite schema (run once on the initializing thread)."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Simulation schemas table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulation_schemas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                tool_version TEXT NOT NULL,
                schema_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tool_name, tool_version)
            )
        """)

        # Execution results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL UNIQUE,
                simulation_name TEXT NOT NULL,
                simulation_version TEXT NOT NULL,
                schema_id INTEGER REFERENCES simulation_schemas(id),
                squid_id TEXT UNIQUE,
                input_params TEXT NOT NULL,
                output_params TEXT,
                status TEXT DEFAULT 'pending',
                duration_seconds REAL,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                run_db_path TEXT,
                metadata TEXT
            )
        """)

        # Parameter definitions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parameter_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_id INTEGER REFERENCES simulation_schemas(id),
                param_name TEXT NOT NULL,
                param_type TEXT NOT NULL,
                classification TEXT NOT NULL,
                label TEXT,
                description TEXT,
                units TEXT,
                min_value REAL,
                max_value REAL,
                default_value TEXT,
                choices TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Result errors table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS result_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT,
                simulation_name TEXT NOT NULL,
                simulation_version TEXT,
                error_type TEXT,
                error_message TEXT NOT NULL,
                stack_trace TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_results_exec_id ON execution_results(execution_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_results_simulation ON execution_results(simulation_name, simulation_version)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exec_results_squid ON execution_results(squid_id)")
        self._ensure_sqlite_result_constraints(cursor)

        conn.commit()

    def _ensure_sqlite_result_constraints(self, cursor):
        """Apply result-table constraints required by SQLite upsert paths."""
        cursor.execute("UPDATE execution_results SET squid_id = NULL WHERE squid_id = ''")
        cursor.execute("""
            UPDATE execution_results
            SET squid_id = NULL
            WHERE squid_id IS NOT NULL
              AND id NOT IN (
                  SELECT MAX(id)
                  FROM execution_results
                  WHERE squid_id IS NOT NULL
                  GROUP BY squid_id
              )
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_exec_results_execution_id
            ON execution_results(execution_id)
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_exec_results_squid
            ON execution_results(squid_id)
        """)

    def register_schema(
        self,
        tool_name: str,
        tool_version: str,
        schema_data: Dict[str, Any]
    ) -> int:
        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        schema_json = json.dumps(schema_data)

        cursor.execute("""
            INSERT INTO simulation_schemas (tool_name, tool_version, schema_data, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(tool_name, tool_version) DO UPDATE SET
                schema_data = excluded.schema_data,
                updated_at = CURRENT_TIMESTAMP
        """, (tool_name, tool_version, schema_json))

        conn.commit()

        cursor.execute("""
            SELECT id FROM simulation_schemas
            WHERE tool_name = ? AND tool_version = ?
        """, (tool_name, tool_version))

        result = cursor.fetchone()
        return result[0] if result else None

    def register_result(
        self,
        execution_id: str,
        simulation_name: str,
        simulation_version: str,
        squid_id: str,
        input_params: Dict[str, Any],
        output_params: Dict[str, Any],
        status: str,
        duration_seconds: Optional[float],
        run_db_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        # Get schema_id
        cursor.execute("""
            SELECT id FROM simulation_schemas
            WHERE tool_name = ? AND tool_version = ?
        """, (simulation_name, simulation_version))
        result = cursor.fetchone()
        schema_id = result[0] if result else None

        input_json = json.dumps(input_params)
        output_json = json.dumps(output_params) if output_params else None
        metadata_json = json.dumps(metadata) if metadata else None
        normalized_squid_id = squid_id or None
        conflict_key = "squid_id" if normalized_squid_id is not None else "execution_id"

        cursor.execute(f"""
            INSERT INTO execution_results (
                execution_id, simulation_name, simulation_version, schema_id,
                squid_id, input_params, output_params, status, duration_seconds,
                run_db_path, metadata, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT({conflict_key}) DO UPDATE SET
                output_params = excluded.output_params,
                status = excluded.status,
                duration_seconds = excluded.duration_seconds,
                completed_at = CURRENT_TIMESTAMP
        """, (execution_id, simulation_name, simulation_version, schema_id,
              normalized_squid_id, input_json, output_json, status, duration_seconds,
              run_db_path, metadata_json))

        conn.commit()
        return cursor.lastrowid

    def _matches_filter(self, value: Any, filter_spec: Any) -> bool:
        """Check if a value matches a filter specification.

        Filter can be:
        - Simple value: value == filter_spec
        - Dict with operators: {'$gt': 100, '$lt': 200}
        """
        if isinstance(filter_spec, dict):
            # Handle comparison operators
            for op, target in filter_spec.items():
                if op == '$gt':
                    if not (value is not None and value > target):
                        return False
                elif op == '$gte':
                    if not (value is not None and value >= target):
                        return False
                elif op == '$lt':
                    if not (value is not None and value < target):
                        return False
                elif op == '$lte':
                    if not (value is not None and value <= target):
                        return False
                elif op == '$eq':
                    if value != target:
                        return False
                else:
                    # Unknown operator, ignore
                    pass
            return True
        else:
            # Simple equality check
            return value == filter_spec

    def search_results(
        self,
        simulation_name: Optional[str] = None,
        simulation_version: Optional[str] = None,
        status: Optional[str] = None,
        input_filters: Optional[Dict[str, Any]] = None,
        output_filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        import json
        cursor = self._get_conn().cursor()

        query = """
            SELECT execution_id, simulation_name, simulation_version, squid_id,
                   input_params, output_params, status, created_at
            FROM execution_results
            WHERE 1=1
        """
        params = []

        if simulation_name:
            query += " AND simulation_name = ?"
            params.append(simulation_name)

        if simulation_version:
            query += " AND simulation_version = ?"
            params.append(simulation_version)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            result = {
                'execution_id': row['execution_id'],
                'simulation_name': row['simulation_name'],
                'simulation_version': row['simulation_version'],
                'squid_id': row['squid_id'],
                'input_params': json.loads(row['input_params']) if row['input_params'] else {},
                'output_params': json.loads(row['output_params']) if row['output_params'] else {},
                'status': row['status'],
                'created_at': row['created_at']
            }

            # Filter by input params (with operator support)
            if input_filters:
                match = all(
                    self._matches_filter(result['input_params'].get(k), v)
                    for k, v in input_filters.items()
                )
                if not match:
                    continue

            # Filter by output params (with operator support)
            if output_filters:
                match = all(
                    self._matches_filter(result['output_params'].get(k), v)
                    for k, v in output_filters.items()
                )
                if not match:
                    continue

            results.append(result)

        return results

    def get_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        import json
        cursor = self._get_conn().cursor()

        cursor.execute("""
            SELECT * FROM execution_results WHERE execution_id = ?
        """, (execution_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return {
            'id': row['id'],
            'execution_id': row['execution_id'],
            'simulation_name': row['simulation_name'],
            'simulation_version': row['simulation_version'],
            'squid_id': row['squid_id'],
            'input_params': json.loads(row['input_params']),
            'output_params': json.loads(row['output_params']) if row['output_params'] else None,
            'status': row['status'],
            'duration_seconds': row['duration_seconds'],
            'created_at': row['created_at'],
            'completed_at': row['completed_at'],
            'run_db_path': row['run_db_path'],
            'metadata': json.loads(row['metadata']) if row['metadata'] else None
        }

    def delete_result(self, execution_id: str) -> Tuple[Dict[str, Any], int]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM result_errors WHERE execution_id = ?", (execution_id,))
        cursor.execute("DELETE FROM execution_results WHERE execution_id = ?", (execution_id,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count == 0:
            return {'error': 'Result not found'}, 404

        return {'status': 'deleted', 'execution_id': execution_id}, 200

    def get_parameter_stats(
        self,
        simulation_name: str,
        param_name: str,
        param_class: str = 'output'
    ) -> Dict[str, Any]:
        import json
        cursor = self._get_conn().cursor()

        param_column = 'output_params' if param_class == 'output' else 'input_params'

        cursor.execute(f"""
            SELECT {param_column} FROM execution_results
            WHERE simulation_name = ?
        """, (simulation_name,))

        values = []
        for row in cursor.fetchall():
            params = json.loads(row[0]) if row[0] else {}
            if param_name in params:
                try:
                    values.append(float(params[param_name]))
                except (ValueError, TypeError):
                    pass

        if not values:
            return {
                'param_name': param_name,
                'count': 0
            }

        return {
            'param_name': param_name,
            'param_type': 'number',
            'min_value': min(values),
            'max_value': max(values),
            'avg_value': sum(values) / len(values),
            'count': len(values)
        }

    def record_error(
        self,
        execution_id: Optional[str],
        simulation_name: str,
        simulation_version: Optional[str],
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None
    ) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO result_errors (
                execution_id, simulation_name, simulation_version,
                error_type, error_message, stack_trace
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (execution_id, simulation_name, simulation_version,
              error_type, error_message, stack_trace))

        conn.commit()


class PostgreSQLResultsBackend(ResultsBackend):
    """PostgreSQL implementation using the results_db_schema.sql schema.

    Uses a per-thread connection pool (threading.local) for thread safety
    under concurrent Flask requests. Uses RealDictCursor for named column
    access, avoiding fragile positional index mapping.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url
        self._local = threading.local()
        # Initialize schema on the calling thread
        self._initialize_schema()

    def _get_conn(self):
        """Return the per-thread PostgreSQL connection, creating it if needed."""
        import psycopg2
        import psycopg2.extras

        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed:
            conn = psycopg2.connect(
                self.db_url,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            conn.autocommit = False
            psycopg2.extras.register_json(conn, globally=False)
            self._local.conn = conn
        return conn

    def _initialize_schema(self):
        """Initialize PostgreSQL schema from SQL file."""
        # Schema is already initialized by Docker or previous service startup
        # The SQL file contains IF NOT EXISTS clauses, so it's safe to skip
        # if objects already exist
        logger.debug("PostgreSQL schema already initialized (via Docker or previous startup)")

    def register_schema(
        self,
        tool_name: str,
        tool_version: str,
        schema_data: Dict[str, Any]
    ) -> int:
        import json
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT register_simulation_schema(%s, %s, %s::jsonb)
        """, (tool_name, tool_version, json.dumps(schema_data)))

        result = cursor.fetchone()
        conn.commit()
        return list(result.values())[0] if result else None

    def register_result(
        self,
        execution_id: str,
        simulation_name: str,
        simulation_version: str,
        squid_id: str,
        input_params: Dict[str, Any],
        output_params: Dict[str, Any],
        status: str,
        duration_seconds: Optional[float],
        run_db_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        import json
        conn = self._get_conn()
        cursor = conn.cursor()
        normalized_squid_id = squid_id or None

        cursor.execute("""
            SELECT register_execution_result(
                %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s::jsonb
            )
        """, (execution_id, simulation_name, simulation_version, normalized_squid_id,
              json.dumps(input_params), json.dumps(output_params),
              status, duration_seconds, run_db_path,
              json.dumps(metadata) if metadata else None))

        result = cursor.fetchone()
        conn.commit()
        return list(result.values())[0] if result else None

    def search_results(
        self,
        simulation_name: Optional[str] = None,
        simulation_version: Optional[str] = None,
        status: Optional[str] = None,
        input_filters: Optional[Dict[str, Any]] = None,
        output_filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        import json
        cursor = self._get_conn().cursor()

        cursor.execute("""
            SELECT * FROM search_results_by_params(
                %s, %s, %s, %s::jsonb, %s::jsonb, %s
            )
        """, (simulation_name,
              simulation_version,
              status,
              json.dumps(input_filters or {}),
              json.dumps(output_filters or {}),
              limit))

        rows = cursor.fetchall()
        results = []

        for row in rows:
            results.append({
                'execution_id': row['execution_id'],
                'simulation_name': row['simulation_name'],
                'simulation_version': row['simulation_version'],
                'squid_id': row['squid_id'],
                'input_params': row['input_params'],
                'output_params': row['output_params'],
                'status': row['status'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            })

        return results

    def get_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._get_conn().cursor()

        cursor.execute("""
            SELECT * FROM execution_results WHERE execution_id = %s
        """, (execution_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return {
            'id': row['id'],
            'execution_id': row['execution_id'],
            'simulation_name': row['simulation_name'],
            'simulation_version': row['simulation_version'],
            'squid_id': row['squid_id'],
            'input_params': row['input_params'],
            'output_params': row['output_params'],
            'status': row['status'],
            'duration_seconds': row['duration_seconds'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
            'run_db_path': row['run_db_path'],
            'metadata': row['metadata'],
        }

    def delete_result(self, execution_id: str) -> Tuple[Dict[str, Any], int]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM result_errors WHERE execution_id = %s", (execution_id,))
        cursor.execute("DELETE FROM execution_results WHERE execution_id = %s", (execution_id,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count == 0:
            return {'error': 'Result not found'}, 404

        return {'status': 'deleted', 'execution_id': execution_id}, 200

    def get_parameter_stats(
        self,
        simulation_name: str,
        param_name: str,
        param_class: str = 'output'
    ) -> Dict[str, Any]:
        cursor = self._get_conn().cursor()

        cursor.execute("""
            SELECT * FROM get_parameter_statistics(%s, %s, %s)
        """, (simulation_name, param_name, param_class))

        row = cursor.fetchone()
        if not row or row.get('count', row.get('total_count', 0)) == 0:
            return {'param_name': param_name, 'count': 0}

        return {
            'param_name': row.get('param_name', param_name),
            'param_type': row.get('param_type'),
            'min_value': float(row['min_value']) if row.get('min_value') is not None else None,
            'max_value': float(row['max_value']) if row.get('max_value') is not None else None,
            'avg_value': float(row['avg_value']) if row.get('avg_value') is not None else None,
            'count': row.get('count', row.get('total_count', 0)),
        }

    def record_error(
        self,
        execution_id: Optional[str],
        simulation_name: str,
        simulation_version: Optional[str],
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None
    ) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO result_errors (
                execution_id, simulation_name, simulation_version,
                error_type, error_message, stack_trace
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (execution_id, simulation_name, simulation_version,
              error_type, error_message, stack_trace))

        conn.commit()


# ============================================================================
# Result Introspector
# ============================================================================

class ResultIntrospector:
    """
    Introspects simulation results from run databases.

    Extracts parameter schemas and values for searchable storage.
    """

    @staticmethod
    def introspect_run(execution_id: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Introspect a run database and extract parameters.

        Returns:
            Tuple of (schema, input_params, output_params)
        """
        run_db = RunDatabase(execution_id)

        # Get run metadata
        summary = run_db.get_summary()

        # Get inputs
        inputs = run_db.get_inputs()
        input_schema = {}
        input_params = {}

        for inp in inputs:
            param_name = inp['name']
            input_params[param_name] = inp['value']

            input_schema[param_name] = {
                'type': inp['field_type'],
                'label': param_name,
                'description': inp.get('metadata', {}).get('description', ''),
                'units': inp.get('units'),
                'default': inp['value']
            }

        # Get outputs
        outputs = run_db.get_outputs()
        output_schema = {}
        output_params = {}

        for out in outputs:
            param_name = out['name']
            output_params[param_name] = out['value']

            output_schema[param_name] = {
                'type': out['field_type'],
                'label': param_name,
                'description': out.get('metadata', {}).get('description', ''),
                'units': out.get('units')
            }

        schema = {
            'input': input_schema,
            'output': output_schema
        }

        return schema, input_params, output_params


# ============================================================================
# Flask Service
# ============================================================================

def create_results_service(
    backend: str = 'sqlite',
    db_path: str = None,
    db_url: str = None,
    require_auth: bool = True
) -> Flask:
    """Create the Results Service Flask app."""

    app = Flask(__name__)

    # Initialize backend
    if backend == 'sqlite':
        results_backend = SQLiteResultsBackend(db_path)
    elif backend == 'postgresql':
        if not db_url:
            raise ValueError("db_url required for PostgreSQL backend")
        results_backend = PostgreSQLResultsBackend(db_url)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    def check_session():
        """Check session authentication."""
        if not require_auth:
            return None

        session_id = request.headers.get('X-Session-ID')
        if not session_id:
            return jsonify({'error': 'Missing session ID'}), 401

        session_mgr = get_session_manager()
        session = session_mgr.get_session(session_id)

        if not session or not session.is_valid():
            return jsonify({'error': 'Invalid session'}), 401

        return session

    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        return jsonify({
            'status': 'healthy',
            'service': 'results',
            'backend': backend
        })

    @app.route('/register', methods=['POST'])
    def register_result():
        """Register a simulation result."""
        auth_result = check_session()
        if isinstance(auth_result, tuple):
            return auth_result

        data = request.json
        execution_id = data.get('execution_id')

        if not execution_id:
            return jsonify({'error': 'execution_id required'}), 400

        try:
            # Introspect the run
            schema, input_params, output_params = ResultIntrospector.introspect_run(execution_id)

            # Get run summary for metadata
            run_db = RunDatabase(execution_id)
            summary = run_db.get_summary()

            # Register schema
            schema_id = results_backend.register_schema(
                summary['simulation_name'],
                summary['simulation_version'],
                schema
            )

            # Register result
            result_id = results_backend.register_result(
                execution_id=execution_id,
                simulation_name=summary['simulation_name'],
                simulation_version=summary['simulation_version'],
                squid_id=data.get('squid_id', f"{summary['simulation_name']}/{summary['simulation_version']}/{execution_id}"),
                input_params=input_params,
                output_params=output_params,
                status=summary['status'],
                duration_seconds=summary.get('duration_seconds'),
                run_db_path=run_db.db_path,
                metadata=data.get('metadata')
            )

            return jsonify({
                'success': True,
                'result_id': result_id,
                'schema_id': schema_id
            })

        except Exception as e:
            logger.error(f"Error registering result: {e}", exc_info=True)

            # Record error
            results_backend.record_error(
                execution_id=execution_id,
                simulation_name=data.get('simulation_name', 'unknown'),
                simulation_version=data.get('simulation_version'),
                error_type=type(e).__name__,
                error_message=str(e)
            )

            return jsonify({'error': str(e)}), 500

    @app.route('/register_direct', methods=['POST'])
    def register_result_direct():
        """Register a simulation result directly (without RunDatabase introspection)."""
        auth_result = check_session()
        if isinstance(auth_result, tuple):
            return auth_result

        data = request.json
        logger.debug(f"POST /register_direct - Execution: {data.get('execution_id', 'unknown')}")

        # Validate required fields
        required_fields = ['execution_id', 'simulation_name', 'simulation_version',
                          'input_params', 'output_params', 'status']
        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field: {field}")
                return jsonify({'error': f'{field} required'}), 400

        logger.debug(f"Registering result - Sim: {data['simulation_name']}, Status: {data['status']}")
        try:
            # Build schema from input/output params
            schema = {
                'inputs': {},
                'outputs': {}
            }

            # Infer types from parameter values
            for param_name, param_value in data['input_params'].items():
                param_type = type(param_value).__name__
                if param_type == 'float' or param_type == 'int':
                    param_type = 'number'
                elif param_type == 'str':
                    param_type = 'string'
                elif param_type == 'bool':
                    param_type = 'boolean'

                schema['inputs'][param_name] = {
                    'type': param_type,
                    'unit': None
                }

            for param_name, param_value in data['output_params'].items():
                param_type = type(param_value).__name__
                if param_type == 'float' or param_type == 'int':
                    param_type = 'number'
                elif param_type == 'str':
                    param_type = 'string'
                elif param_type == 'bool':
                    param_type = 'boolean'

                schema['outputs'][param_name] = {
                    'type': param_type,
                    'unit': None
                }

            # Register schema
            schema_id = results_backend.register_schema(
                data['simulation_name'],
                data['simulation_version'],
                schema
            )

            # Register result
            logger.debug(f"Registering schema for {data['simulation_name']} v{data['simulation_version']}")
            result_id = results_backend.register_result(
                execution_id=data['execution_id'],
                simulation_name=data['simulation_name'],
                simulation_version=data['simulation_version'],
                squid_id=data.get('squid_id') or None,
                input_params=data['input_params'],
                output_params=data['output_params'],
                status=data['status'],
                duration_seconds=data.get('duration_seconds'),
                run_db_path=data.get('run_db_path', ''),
                metadata=data.get('metadata')
            )

            logger.debug(f"Successfully registered result - ID: {result_id}, Schema ID: {schema_id}")
            return jsonify({
                'success': True,
                'result_id': result_id,
                'schema_id': schema_id
            })

        except Exception as e:
            logger.error(f"Error registering result directly: {e}", exc_info=True)

            # Record error
            results_backend.record_error(
                execution_id=data.get('execution_id', 'unknown'),
                simulation_name=data.get('simulation_name', 'unknown'),
                simulation_version=data.get('simulation_version'),
                error_type=type(e).__name__,
                error_message=str(e)
            )

            return jsonify({'error': str(e)}), 500

    @app.route('/search', methods=['POST'])
    def search_results():
        """Search results by parameters."""
        auth_result = check_session()
        if isinstance(auth_result, tuple):
            return auth_result

        data = request.json
        simulation_name = data.get('simulation_name')
        simulation_version = data.get('simulation_version')
        status = data.get('status')
        input_filters = data.get('input_filters', {})
        output_filters = data.get('output_filters', {})
        limit = data.get('limit', 100)

        logger.debug(f"Search request - sim: {simulation_name}, version: {simulation_version}, status: {status}")
        logger.debug(f"Input filters: {input_filters}")
        logger.debug(f"Output filters: {output_filters}")

        results = results_backend.search_results(
            simulation_name=simulation_name,
            simulation_version=simulation_version,
            status=status,
            input_filters=input_filters,
            output_filters=output_filters,
            limit=limit
        )

        logger.debug(f"Search returned {len(results)} results")

        return jsonify({
            'results': results,
            'count': len(results)
        })

    @app.route('/results/<path:execution_id>', methods=['GET'])
    def get_result(execution_id):
        """Get a specific result."""
        auth_result = check_session()
        if isinstance(auth_result, tuple):
            return auth_result

        result = results_backend.get_result(execution_id)

        if not result:
            return jsonify({'error': 'Result not found'}), 404

        return jsonify(result)

    @app.route('/results/<path:execution_id>', methods=['DELETE'])
    def delete_result(execution_id):
        """Delete a specific result."""
        auth_result = check_session()
        if isinstance(auth_result, tuple):
            return auth_result

        result, status = results_backend.delete_result(execution_id)
        return jsonify(result), status

    @app.route('/results', methods=['DELETE'])
    def clear_all_results():
        """Delete all results."""
        auth_result = check_session()
        if isinstance(auth_result, tuple):
            return auth_result

        try:
            all_results = results_backend.search_results(
                simulation_name=None, input_filters={}, output_filters={}, limit=100000
            )
            deleted = 0
            for r in all_results:
                _, status = results_backend.delete_result(r["execution_id"])
                if status == 200:
                    deleted += 1
            return jsonify({"deleted": deleted}), 200
        except Exception as exc:
            app.logger.error(f"Clear all results failed: {exc}")
            return jsonify({"error": "Internal server error"}), 500

    @app.route('/stats/<simulation_name>/<param_name>', methods=['GET'])
    def get_parameter_stats(simulation_name, param_name):
        """Get parameter statistics."""
        auth_result = check_session()
        if isinstance(auth_result, tuple):
            return auth_result

        param_class = request.args.get('class', 'output')

        stats = results_backend.get_parameter_stats(
            simulation_name=simulation_name,
            param_name=param_name,
            param_class=param_class
        )

        return jsonify(stats)

    return app


def main():
    """Main entry point for running the service."""
    import argparse

    parser = argparse.ArgumentParser(description='Sim2l Results Service')
    parser.add_argument('--backend', choices=['sqlite', 'postgresql'],
                        default='sqlite', help='Database backend')
    parser.add_argument('--db-path', help='SQLite database path')
    parser.add_argument('--db-url', help='PostgreSQL connection URL')
    parser.add_argument('--port', type=int, default=8003,
                        help='Port to run on')
    parser.add_argument('--host', default='0.0.0.0',
                        help='Host to bind to')
    parser.add_argument('--no-auth', action='store_true',
                        help='Disable authentication')
    parser.add_argument('--debug', action='store_true',
                        help='Enable DEBUG logging')

    args = parser.parse_args()

    # Set logging level based on --debug flag
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )
    if args.debug:
        logger.debug("DEBUG logging enabled")

    app = create_results_service(
        backend=args.backend,
        db_path=args.db_path,
        db_url=args.db_url,
        require_auth=not args.no_auth
    )

    logger.info(f"Starting Results Service on {args.host}:{args.port}")
    logger.info(f"Backend: {args.backend}")

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
