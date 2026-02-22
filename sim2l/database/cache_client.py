# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Cache service client for distributed caching.

Connects to a remote cache service (PostgreSQL or Redis-backed)
with session-based authentication.
"""

import requests
import logging
from typing import Dict, Optional, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class CacheClient:
    """
    Client for remote cache service.

    Provides distributed caching across multiple sim2l installations
    with session-based access control.
    """

    def __init__(
        self,
        service_url: str,
        session_id: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize cache client.

        Args:
            service_url: URL of cache service (e.g., 'http://localhost:8001')
            session_id: Session ID for authentication
            timeout: Request timeout in seconds
        """
        self.service_url = service_url.rstrip("/")
        self.session_id = session_id
        self.timeout = timeout
        self._session = requests.Session()

        if session_id:
            self._session.headers.update({"X-Session-ID": session_id})

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a cache entry.

        Args:
            cache_key: Cache key to lookup

        Returns:
            Dict with execution_id, squid_id, run_db_path, metadata if found, else None
        """
        try:
            response = self._session.get(
                f"{self.service_url}/cache/{cache_key}",
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Cache hit for key {cache_key[:16]}...")
                return data
            elif response.status_code == 404:
                logger.debug(f"Cache miss for key {cache_key[:16]}...")
                return None
            elif response.status_code == 401:
                logger.error("Unauthorized: Invalid or expired session")
                return None
            else:
                logger.error(
                    f"Cache lookup failed: {response.status_code} {response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Cache service request failed: {e}")
            return None

    def set(
        self,
        cache_key: str,
        simulation_id: int,
        simulation_name: str,
        simulation_version: str,
        execution_id: str,
        squid_id: str,
        input_hash: str,
        run_db_path: str,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Set a cache entry.

        Args:
            cache_key: Cache key
            simulation_id: Simulation ID
            simulation_name: Simulation name
            simulation_version: Simulation version
            execution_id: Execution ID
            squid_id: SQUID ID
            input_hash: Hash of inputs
            run_db_path: Path to per-run database
            ttl_seconds: Time-to-live in seconds (None = no expiration)
            metadata: Additional metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            payload = {
                "cache_key": cache_key,
                "simulation_id": simulation_id,
                "simulation_name": simulation_name,
                "simulation_version": simulation_version,
                "execution_id": execution_id,
                "squid_id": squid_id,
                "input_hash": input_hash,
                "run_db_path": run_db_path,
                "ttl_seconds": ttl_seconds,
                "metadata": metadata,
            }

            response = self._session.post(
                f"{self.service_url}/cache",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                logger.info(f"Cache set for key {cache_key[:16]}...")
                return True
            elif response.status_code == 401:
                logger.error("Unauthorized: Invalid or expired session")
                return False
            else:
                logger.error(f"Cache set failed: {response.status_code} {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Cache service request failed: {e}")
            return False

    def invalidate(
        self,
        simulation_id: Optional[int] = None,
        simulation_name: Optional[str] = None,
        simulation_version: Optional[str] = None,
        pattern: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> int:
        """
        Invalidate cache entries.

        Args:
            simulation_id: Invalidate all entries for this simulation ID
            simulation_name: Invalidate all entries for this simulation name
            simulation_version: Invalidate all entries for this version
            pattern: SQL LIKE pattern for cache keys
            reason: Reason for invalidation

        Returns:
            Number of entries invalidated, or -1 on error
        """
        try:
            payload = {
                "simulation_id": simulation_id,
                "simulation_name": simulation_name,
                "simulation_version": simulation_version,
                "pattern": pattern,
                "reason": reason,
            }

            response = self._session.post(
                f"{self.service_url}/cache/invalidate",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()
                count = data.get("invalidated_count", 0)
                logger.info(f"Invalidated {count} cache entries")
                return count
            elif response.status_code == 401:
                logger.error("Unauthorized: Invalid or expired session")
                return -1
            else:
                logger.error(
                    f"Cache invalidation failed: {response.status_code} {response.text}"
                )
                return -1

        except requests.exceptions.RequestException as e:
            logger.error(f"Cache service request failed: {e}")
            return -1

    def get_stats(
        self, simulation_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cache statistics.

        Args:
            simulation_id: Get stats for specific simulation (None = global stats)

        Returns:
            Dict with cache statistics or None on error
        """
        try:
            params = {}
            if simulation_id is not None:
                params["simulation_id"] = simulation_id

            response = self._session.get(
                f"{self.service_url}/cache/stats",
                params=params,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to get cache stats: {response.status_code} {response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Cache service request failed: {e}")
            return None

    def health_check(self) -> bool:
        """
        Check if cache service is healthy.

        Returns:
            True if service is reachable and healthy, False otherwise
        """
        try:
            response = self._session.get(
                f"{self.service_url}/health",
                timeout=5,
            )
            return response.status_code == 200

        except requests.exceptions.RequestException:
            return False


class LocalCacheClient:
    """
    Local in-memory cache implementation for development/testing.

    Provides the same interface as CacheClient but stores cache entries
    in memory. Does not require a remote service.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._stats = {
            "requests": 0,
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0,
        }

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get a cache entry from local cache."""
        self._stats["requests"] += 1

        entry = self._cache.get(cache_key)

        if entry is None:
            self._stats["misses"] += 1
            logger.debug(f"Local cache miss for key {cache_key[:16]}...")
            return None

        # Check expiration
        expires_at = entry.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
            self._stats["misses"] += 1
            del self._cache[cache_key]
            logger.debug(f"Local cache expired for key {cache_key[:16]}...")
            return None

        self._stats["hits"] += 1
        logger.info(f"Local cache hit for key {cache_key[:16]}...")

        return {
            "execution_id": entry["execution_id"],
            "squid_id": entry["squid_id"],
            "run_db_path": entry["run_db_path"],
            "metadata": entry.get("metadata"),
        }

    def set(
        self,
        cache_key: str,
        simulation_id: int,
        simulation_name: str,
        simulation_version: str,
        execution_id: str,
        squid_id: str,
        input_hash: str,
        run_db_path: str,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Set a cache entry in local cache."""
        from datetime import timedelta

        self._stats["sets"] += 1

        expires_at = None
        if ttl_seconds is not None:
            expires_at = (
                datetime.utcnow() + timedelta(seconds=ttl_seconds)
            ).isoformat()

        self._cache[cache_key] = {
            "simulation_id": simulation_id,
            "simulation_name": simulation_name,
            "simulation_version": simulation_version,
            "execution_id": execution_id,
            "squid_id": squid_id,
            "input_hash": input_hash,
            "run_db_path": run_db_path,
            "expires_at": expires_at,
            "metadata": metadata,
            "created_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Local cache set for key {cache_key[:16]}...")
        return True

    def invalidate(
        self,
        simulation_id: Optional[int] = None,
        simulation_name: Optional[str] = None,
        simulation_version: Optional[str] = None,
        pattern: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> int:
        """Invalidate cache entries in local cache."""
        count = 0

        keys_to_remove = []
        for key, entry in self._cache.items():
            should_invalidate = True

            if simulation_id is not None and entry["simulation_id"] != simulation_id:
                should_invalidate = False

            if (
                simulation_name is not None
                and entry["simulation_name"] != simulation_name
            ):
                should_invalidate = False

            if (
                simulation_version is not None
                and entry["simulation_version"] != simulation_version
            ):
                should_invalidate = False

            if pattern is not None:
                # Simple pattern matching (SQL LIKE % = Python *)
                import re

                regex_pattern = pattern.replace("%", ".*")
                if not re.match(regex_pattern, key):
                    should_invalidate = False

            if should_invalidate:
                keys_to_remove.append(key)
                count += 1

        for key in keys_to_remove:
            del self._cache[key]

        self._stats["invalidations"] += count

        if count > 0:
            logger.info(f"Invalidated {count} local cache entries")

        return count

    def get_stats(
        self, simulation_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Get cache statistics."""
        hit_rate = 0
        if self._stats["requests"] > 0:
            hit_rate = 100.0 * self._stats["hits"] / self._stats["requests"]

        stats = {
            "total_requests": self._stats["requests"],
            "cache_hits": self._stats["hits"],
            "cache_misses": self._stats["misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "total_entries": len(self._cache),
            "total_sets": self._stats["sets"],
            "total_invalidations": self._stats["invalidations"],
        }

        if simulation_id is not None:
            # Filter by simulation
            sim_entries = [
                e for e in self._cache.values() if e["simulation_id"] == simulation_id
            ]
            stats["simulation_entries"] = len(sim_entries)

        return stats

    def health_check(self) -> bool:
        """Local cache is always healthy."""
        return True
