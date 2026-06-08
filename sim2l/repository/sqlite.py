# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""SQLite storage backend implementation"""

import sqlite3
import json
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from .backend import StorageBackend
from ..definition import SimulationDefinition
from ..definition.function_workflow import function_from_source
from ..schema import InputSchema, OutputSchema
from ..config import get_logger

logger = get_logger()


class SQLiteBackend(StorageBackend):
    """SQLite storage backend.

    Uses a per-thread connection pool (``threading.local``) so concurrent
    callers each get their own SQLite connection. WAL journal mode is
    enabled for better read concurrency under load.
    """

    def __init__(self, db_path: Path):
        """Initialize SQLite backend

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._ensure_database()

    def _ensure_database(self):
        """Ensure database exists and has correct schema"""
        if not self.db_path.exists():
            self._create_database()

    def _create_database(self):
        """Create database with schema"""
        logger.info(f"Creating database at {self.db_path}")

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Read schema SQL
        schema_file = Path(__file__).parent / "schema.sql"
        with open(schema_file, 'r') as f:
            schema_sql = f.read()

        # Create database and tables (using a fresh connection so the per-thread
        # pool doesn't end up holding a long-lived handle to a freshly created
        # file with stale metadata).
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def create_database(cls, db_path: Path):
        """Create a new database

        Args:
            db_path: Path to database file
        """
        backend = cls(db_path)
        backend._create_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Return the per-thread connection, opening one if needed.

        Replaces the previous open-on-every-call pattern, which serialized
        all access through SQLite's file lock. The first call from a given
        thread also enables WAL mode for better read concurrency.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # column access by name
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                # WAL mode isn't supported on all filesystems (eg. some NFS
                # mounts). Continue with the default journal mode rather than
                # failing hard.
                pass
            # FK enforcement is OFF by default in SQLite — the schema's
            # ON DELETE CASCADE clauses silently no-op without this PRAGMA.
            # Review item #C5.
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def deploy(self, simulation: SimulationDefinition) -> int:
        """Deploy a simulation to database"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Serialize schemas
            input_schema_json = json.dumps(simulation.inputs.to_dict())
            output_schema_json = json.dumps(simulation.outputs.to_dict())

            # Get workflow bytes
            workflow_bytes = simulation.get_workflow_bytes()

            # Serialize metadata
            tags_json = json.dumps(simulation.tags)
            dependencies_json = json.dumps(simulation.dependencies)

            # Insert simulation
            cursor.execute("""
                INSERT INTO simulations (
                    name, version, description, author, tags,
                    input_schema, output_schema,
                    workflow_type, workflow_data, workflow_hash,
                    dependencies, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                simulation.name,
                simulation.version,
                simulation.description,
                simulation.author,
                tags_json,
                input_schema_json,
                output_schema_json,
                simulation.workflow_type,
                workflow_bytes,
                simulation.workflow_hash,
                dependencies_json,
                'active',
            ))

            simulation_id = cursor.lastrowid

            # Insert tags into simulation_tags table
            for tag in simulation.tags:
                cursor.execute("""
                    INSERT INTO simulation_tags (simulation_id, tag)
                    VALUES (?, ?)
                """, (simulation_id, tag))

            conn.commit()
            logger.info(f"Deployed simulation {simulation.name} v{simulation.version} (ID: {simulation_id})")

            return simulation_id

        except sqlite3.IntegrityError as e:
            conn.rollback()
            raise ValueError(f"Simulation {simulation.name} v{simulation.version} already exists") from e

    def load(self, name: str, version: Optional[str] = None) -> SimulationDefinition:
        """Load a simulation from database"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if version is None:
            # Load latest version
            cursor.execute("""
                SELECT * FROM simulations
                WHERE name = ? AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
            """, (name,))
        else:
            cursor.execute("""
                SELECT * FROM simulations
                WHERE name = ? AND version = ?
            """, (name, version))

        row = cursor.fetchone()

        if row is None:
            version_str = f"v{version}" if version else "(latest)"
            raise ValueError(f"Simulation {name} {version_str} not found")

        # Deserialize schemas
        input_schema = InputSchema.from_dict(json.loads(row['input_schema']))
        output_schema = OutputSchema.from_dict(json.loads(row['output_schema']))

        # Get workflow
        workflow_bytes = row['workflow_data']
        workflow_type = row['workflow_type']

        # Deserialize workflow based on type
        if workflow_type == 'function':
            workflow = function_from_source(workflow_bytes)
        else:
            # For notebooks, keep as bytes
            workflow = workflow_bytes

        # Deserialize metadata
        tags = json.loads(row['tags']) if row['tags'] else []
        dependencies = json.loads(row['dependencies']) if row['dependencies'] else []

        # Create simulation definition
        sim_def = SimulationDefinition(
            name=row['name'],
            version=row['version'],
            inputs=input_schema,
            outputs=output_schema,
            workflow=workflow,
            description=row['description'] or '',
            author=row['author'] or '',
            tags=tags,
            dependencies=dependencies,
            workflow_type=workflow_type,
        )

        # Store the database ID as metadata
        sim_def._db_id = row['id']

        return sim_def

    def exists(self, name: str, version: str) -> bool:
        """Check if simulation exists"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 1 FROM simulations
            WHERE name = ? AND version = ?
        """, (name, version))

        return cursor.fetchone() is not None

    def list(
        self,
        tags: Optional[List[str]] = None,
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """List available simulations"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if tags:
            # Filter by tags
            placeholders = ','.join('?' * len(tags))
            cursor.execute(f"""
                SELECT DISTINCT s.* FROM simulations s
                JOIN simulation_tags st ON s.id = st.simulation_id
                WHERE st.tag IN ({placeholders}) AND s.status = ?
                ORDER BY s.name, s.version
            """, (*tags, status))
        else:
            cursor.execute("""
                SELECT * FROM simulations
                WHERE status = ?
                ORDER BY name, version
            """, (status,))

        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row['id'],
                'name': row['name'],
                'version': row['version'],
                'description': row['description'],
                'author': row['author'],
                'tags': json.loads(row['tags']) if row['tags'] else [],
                'created_at': row['created_at'],
                'status': row['status'],
            })

        return results

    def delete(self, name: str, version: str):
        """Delete a simulation"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM simulations
            WHERE name = ? AND version = ?
        """, (name, version))

        if cursor.rowcount == 0:
            raise ValueError(f"Simulation {name} v{version} not found")

        conn.commit()
        logger.info(f"Deleted simulation {name} v{version}")

    def update_status(self, name: str, version: str, status: str):
        """Update simulation status"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE simulations
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ? AND version = ?
        """, (status, name, version))

        if cursor.rowcount == 0:
            raise ValueError(f"Simulation {name} v{version} not found")

        conn.commit()
        logger.info(f"Updated simulation {name} v{version} status to {status}")

    def get_simulation_id(self, name: str, version: str) -> Optional[int]:
        """Get simulation ID from name and version"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id FROM simulations
            WHERE name = ? AND version = ?
        """, (name, version))

        row = cursor.fetchone()
        return row['id'] if row else None
