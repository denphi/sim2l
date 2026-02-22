# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Legacy cache adapter for backward compatibility with papers/simtool cache.

This adapter provides compatibility with the old PostgreSQL-based cache system
from the papers implementation while using the new cache architecture.

Old system (papers):
- Database: simtool_cache (PostgreSQL)
- Schema: ID (VARCHAR), VALUES (JSON)
- Tables: simtool_cache_files, etc.
- Direct PostgreSQL access with PsqlModel base class

New system (sim2l):
- Per-run SQLite databases
- Cache service with REST API
- Master catalog registry

This adapter provides:
1. PsqlModel-compatible interface for legacy code
2. Transparent migration between old and new systems
3. Dual-mode operation (can use old or new backend)
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LegacyCacheConfig:
    """Configuration for legacy cache compatibility."""

    # Old papers cache configuration
    DATABASE_NAME = "simtool_cache"
    TABLE_PREFIX = "simtool_cache_"
    HOST = os.getenv("LEGACY_CACHE_HOST", "squiddb.nanohub.org")
    USER_R = os.getenv("LEGACY_CACHE_USER_R", "hub")
    PWD_R = os.getenv("LEGACY_CACHE_PWD_R", "")  # Don't store in code
    USER_W = os.getenv("LEGACY_CACHE_USER_W", "hub_write")
    PWD_W = os.getenv("LEGACY_CACHE_PWD_W", "")  # Don't store in code
    PORT = os.getenv("LEGACY_CACHE_PORT", "5432")

    # Migration mode
    USE_LEGACY_BACKEND = os.getenv("USE_LEGACY_CACHE_BACKEND", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    ENABLE_DUAL_WRITE = os.getenv("ENABLE_DUAL_WRITE_CACHE", "false").lower() in (
        "true",
        "1",
        "yes",
    )


class PsqlModelAdapter:
    """
    Adapter that mimics the old PsqlModel interface.

    Provides backward compatibility for code expecting the papers/simtool
    cache interface while using the new cache system underneath.
    """

    _table = None  # Subclass must set this

    @classmethod
    def _get_connection(cls):
        """Get PostgreSQL connection (for legacy backend)."""
        import psycopg2

        return psycopg2.connect(
            user=LegacyCacheConfig.USER_W,
            password=LegacyCacheConfig.PWD_W,
            host=LegacyCacheConfig.HOST,
            port=LegacyCacheConfig.PORT,
            database=LegacyCacheConfig.DATABASE_NAME,
        )

    @classmethod
    def _to_new_cache_key(cls, legacy_id: str) -> str:
        """Convert legacy ID to new cache key format."""
        # Legacy: arbitrary ID (could be UUID, timestamp-based, etc.)
        # New: hash-based cache key
        # For compatibility, use table name + ID as key
        return f"{cls._table}:{legacy_id}"

    @classmethod
    def _from_cache_entry(cls, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Convert new cache entry to legacy format."""
        if entry and "metadata" in entry:
            # New cache stores metadata, extract legacy VALUES field
            return entry.get("metadata", {}).get("legacy_values", {})
        return entry

    @classmethod
    def find(cls, id: str) -> Optional[Dict[str, Any]]:
        """
        Find entry by ID (legacy interface).

        Compatible with: File.find(id), User.find(id), etc.
        """
        return cls.select(id)

    @classmethod
    def select(cls, id: str) -> Optional[Dict[str, Any]]:
        """
        Select entry by ID (legacy interface).

        Implementation:
        1. If USE_LEGACY_BACKEND: Query old PostgreSQL directly
        2. Otherwise: Query new cache system with adapted key
        """
        if LegacyCacheConfig.USE_LEGACY_BACKEND:
            # Use old PostgreSQL backend
            return cls._select_legacy(id)
        else:
            # Use new cache system
            return cls._select_new(id)

    @classmethod
    def _select_legacy(cls, id: str) -> Optional[Dict[str, Any]]:
        """Select from legacy PostgreSQL backend."""
        try:
            conn = cls._get_connection()
            cursor = conn.cursor()

            sql = f'''SELECT "VALUES"
                FROM "{cls._table}"
                WHERE "ID" = %s;'''

            cursor.execute(sql, (str(id),))
            result = cursor.fetchone()
            conn.close()

            if result is None:
                return None
            else:
                return result[0]

        except Exception as e:
            logger.error(f"Legacy cache select error: {e}")
            return None

    @classmethod
    def _select_new(cls, id: str) -> Optional[Dict[str, Any]]:
        """Select from new cache system."""
        from ..config import get_config
        from .cache_client import CacheClient, LocalCacheClient

        config = get_config()
        cache_key = cls._to_new_cache_key(id)

        # Use appropriate cache client
        if config.cache_service_url:
            cache = CacheClient(
                config.cache_service_url, session_id=config.cache_session_id
            )
        else:
            cache = LocalCacheClient()

        # Get from cache
        entry = cache.get(cache_key)

        if entry:
            # Extract legacy VALUES from metadata
            return cls._from_cache_entry(entry)

        return None

    @classmethod
    def get_all(cls, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get multiple entries by IDs (legacy interface).

        Compatible with: File.get_all([id1, id2, ...])
        """
        if LegacyCacheConfig.USE_LEGACY_BACKEND:
            return cls._get_all_legacy(ids)
        else:
            return cls._get_all_new(ids)

    @classmethod
    def _get_all_legacy(cls, ids: List[str]) -> List[Dict[str, Any]]:
        """Get all from legacy PostgreSQL."""
        try:
            conn = cls._get_connection()
            cursor = conn.cursor()

            placeholders = ", ".join(["%s"] * len(ids))
            sql = f'''SELECT "VALUES"
                FROM "{cls._table}"
                WHERE "ID" IN ({placeholders});'''

            cursor.execute(sql, ids)
            results = cursor.fetchall()
            conn.close()

            if results is None:
                return []
            else:
                return [r[0] for r in results]

        except Exception as e:
            logger.error(f"Legacy cache get_all error: {e}")
            return []

    @classmethod
    def _get_all_new(cls, ids: List[str]) -> List[Dict[str, Any]]:
        """Get all from new cache system."""
        results = []
        for id in ids:
            entry = cls.select(id)
            if entry:
                results.append(entry)
        return results

    @classmethod
    def filter(cls, predicate: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Filter entries by predicate (legacy interface).

        Compatible with: File.filter({'parent_id': '123'})
        """
        if LegacyCacheConfig.USE_LEGACY_BACKEND:
            return cls._filter_legacy(predicate)
        else:
            logger.warning(
                "Filter operation not fully supported in new cache system. "
                "Consider using catalog service for queries."
            )
            return []

    @classmethod
    def _filter_legacy(cls, predicate: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter from legacy PostgreSQL."""
        try:
            conn = cls._get_connection()
            cursor = conn.cursor()

            # Build WHERE clause
            conditions = []
            params = []
            for key, value in predicate.items():
                if key == "tab":
                    conditions.append(f'''"VALUES"->>'{{key}}' LIKE %s''')
                    params.append("%" + json.dumps(value).strip('"') + "%")
                else:
                    conditions.append(f'''"VALUES"->>'{{key}}' = %s''')
                    params.append(json.dumps(value).strip('"'))

            where_clause = " AND ".join(conditions)

            sql = f'''SELECT "VALUES"
                FROM "{cls._table}"
                WHERE {where_clause};'''

            cursor.execute(sql, params)
            results = cursor.fetchall()
            conn.close()

            if results is None:
                return []
            else:
                return [r[0] for r in results]

        except Exception as e:
            logger.error(f"Legacy cache filter error: {e}")
            return []

    @classmethod
    def update(cls, id: str, fields: Dict[str, Any]) -> bool:
        """
        Update entry (legacy interface).

        Compatible with: File.update(id, {'name': 'new_name'})
        """
        if LegacyCacheConfig.USE_LEGACY_BACKEND:
            return cls._update_legacy(id, fields)
        else:
            return cls._update_new(id, fields)

    @classmethod
    def _update_legacy(cls, id: str, fields: Dict[str, Any]) -> bool:
        """Update in legacy PostgreSQL."""
        try:
            # Get existing fields
            old_fields = cls.find(id)
            if old_fields is None:
                old_fields = {}

            # Merge fields
            old_fields.update(fields)
            old_fields.update({"date_modified": datetime.timestamp(datetime.now())})

            conn = cls._get_connection()
            cursor = conn.cursor()

            sql = f'''UPDATE "{cls._table}"
                SET "VALUES" = %s
                WHERE "ID" = %s;'''

            cursor.execute(sql, (json.dumps(old_fields), str(id)))
            conn.commit()
            conn.close()

            # Dual write to new system if enabled
            if LegacyCacheConfig.ENABLE_DUAL_WRITE:
                cls._update_new(id, old_fields)

            return True

        except Exception as e:
            logger.error(f"Legacy cache update error: {e}")
            return False

    @classmethod
    def _update_new(cls, id: str, fields: Dict[str, Any]) -> bool:
        """Update in new cache system."""
        from ..config import get_config
        from .cache_client import CacheClient, LocalCacheClient

        config = get_config()
        cache_key = cls._to_new_cache_key(id)

        # Use appropriate cache client
        if config.cache_service_url:
            cache = CacheClient(
                config.cache_service_url, session_id=config.cache_session_id
            )
        else:
            cache = LocalCacheClient()

        # Set in cache with legacy VALUES in metadata
        try:
            cache.set(
                cache_key=cache_key,
                simulation_id=0,  # Legacy data doesn't have simulation_id
                simulation_name="legacy",
                simulation_version="1.0.0",
                execution_id=f"legacy-{id}",
                squid_id=f"legacy/{cls._table}/{id}",
                input_hash=cache_key,
                run_db_path="",
                metadata={"legacy_values": fields, "legacy_table": cls._table},
            )
            return True

        except Exception as e:
            logger.error(f"New cache update error: {e}")
            return False

    @classmethod
    def insert(cls, id: str, fields: Dict[str, Any]) -> bool:
        """
        Insert new entry (legacy interface).

        Compatible with: File.insert(id, {...})
        """
        if LegacyCacheConfig.USE_LEGACY_BACKEND:
            return cls._insert_legacy(id, fields)
        else:
            return cls._insert_new(id, fields)

    @classmethod
    def _insert_legacy(cls, id: str, fields: Dict[str, Any]) -> bool:
        """Insert into legacy PostgreSQL."""
        try:
            conn = cls._get_connection()
            cursor = conn.cursor()

            sql = f'''INSERT INTO "{cls._table}" ("ID", "VALUES")
                VALUES (%s, %s);'''

            cursor.execute(sql, (str(id), json.dumps(fields)))
            conn.commit()
            conn.close()

            # Dual write to new system if enabled
            if LegacyCacheConfig.ENABLE_DUAL_WRITE:
                cls._insert_new(id, fields)

            return True

        except Exception as e:
            logger.error(f"Legacy cache insert error: {e}")
            return False

    @classmethod
    def _insert_new(cls, id: str, fields: Dict[str, Any]) -> bool:
        """Insert into new cache system."""
        # Same as update for new system
        return cls._update_new(id, fields)

    @classmethod
    def delete(cls, id: str) -> bool:
        """
        Delete entry (legacy interface).

        Compatible with: File.delete(id)
        """
        if LegacyCacheConfig.USE_LEGACY_BACKEND:
            return cls._delete_legacy(id)
        else:
            return cls._delete_new(id)

    @classmethod
    def _delete_legacy(cls, id: str) -> bool:
        """Delete from legacy PostgreSQL."""
        try:
            conn = cls._get_connection()
            cursor = conn.cursor()

            sql = f'''DELETE FROM "{cls._table}"
                WHERE "ID" = %s;'''

            cursor.execute(sql, (str(id),))
            conn.commit()
            conn.close()

            # Dual delete from new system if enabled
            if LegacyCacheConfig.ENABLE_DUAL_WRITE:
                cls._delete_new(id)

            return True

        except Exception as e:
            logger.error(f"Legacy cache delete error: {e}")
            return False

    @classmethod
    def _delete_new(cls, id: str) -> bool:
        """Delete from new cache system."""
        from ..config import get_config
        from .cache_client import CacheClient, LocalCacheClient

        config = get_config()
        cache_key = cls._to_new_cache_key(id)

        # Use appropriate cache client
        if config.cache_service_url:
            cache = CacheClient(
                config.cache_service_url, session_id=config.cache_session_id
            )
        else:
            cache = LocalCacheClient()

        # Invalidate in cache
        try:
            cache.invalidate(pattern=cache_key, reason="Deleted via legacy API")
            return True

        except Exception as e:
            logger.error(f"New cache delete error: {e}")
            return False


class LegacyFileModel(PsqlModelAdapter):
    """Legacy File model adapter."""

    _table = "simtool_cache_files"

    @classmethod
    def create(cls, **kwargs):
        """
        Create file entry (legacy interface).

        Compatible with: File.create(name='...', size=..., ...)
        """
        from datetime import datetime
        from uuid import uuid4

        name = kwargs.get("name")
        size = kwargs.get("size")
        uri = kwargs.get("uri")
        parent = kwargs.get("parent")
        creator = kwargs.get("creator")
        siteName = kwargs.get("siteName")
        url = kwargs.get("url")
        id = kwargs.get(
            "id", datetime.now().strftime("%Y%m-%d%H-%M%S-") + str(uuid4())
        )

        parent_id = "0" if parent is None else parent["id"]

        doc = {
            "name": name,
            "size": size,
            "uri": uri,
            "siteName": siteName,
            "url": url,
            "parent_id": parent_id,
            "creator": creator,
            "is_folder": False,
            "status": True,
            "date_created": datetime.timestamp(datetime.now()),
            "date_modified": datetime.timestamp(datetime.now()),
            "id": id,
        }

        cls.insert(doc["id"], doc)

        return doc


class LegacyUserModel(PsqlModelAdapter):
    """Legacy User model adapter."""

    _table = "simtool_cache_users"


class LegacyFolderModel(PsqlModelAdapter):
    """Legacy Folder model adapter."""

    _table = "simtool_cache_folders"
