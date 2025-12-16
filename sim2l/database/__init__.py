"""
Database services for sim2l.

Provides four database systems:
1. Run Database - Per-run SQLite databases for complete run isolation
2. Cache Service - Remote distributed cache with session-based access control
3. Master Catalog - Central registry for all sim2l tools and versions
4. Results Service - Introspected simulation results with searchable parameters
5. File Manager - File and folder management for sim2l runs
"""

from .run_database import RunDatabase
from .cache_client import CacheClient
from .catalog_client import CatalogClient
from .results_client import ResultsClient
from .session_manager import SessionManager, get_session_manager
from .file_manager import FileManager

__all__ = [
    "RunDatabase",
    "CacheClient",
    "CatalogClient",
    "ResultsClient",
    "SessionManager",
    "get_session_manager",
    "FileManager",
]
