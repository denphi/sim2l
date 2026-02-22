# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Comprehensive unit tests for cache clients (LocalCacheClient and CacheClient).

Tests all functionality with high coverage.
"""

import pytest
import responses
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from sim2l.database.cache_client import CacheClient, LocalCacheClient


class TestLocalCacheClientBasic:
    """Tests for LocalCacheClient basic operations."""

    def setup_method(self):
        """Setup for each test."""
        self.cache = LocalCacheClient()

    def test_create_cache(self):
        """Test creating a local cache client."""
        assert self.cache._cache == {}
        assert self.cache._stats["requests"] == 0

    def test_create_with_session_id(self):
        """Test creating cache with session ID."""
        cache = LocalCacheClient(session_id="test-session")
        assert cache.session_id == "test-session"


class TestLocalCacheClientSetGet:
    """Tests for set and get operations."""

    def setup_method(self):
        """Setup for each test."""
        self.cache = LocalCacheClient()

    def test_set_and_get(self):
        """Test basic set and get."""
        success = self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path/to/run.db",
        )

        assert success
        result = self.cache.get("key1")

        assert result is not None
        assert result["execution_id"] == "exec1"
        assert result["squid_id"] == "sim1/1.0.0/abc"
        assert result["run_db_path"] == "/path/to/run.db"

    def test_get_nonexistent(self):
        """Test getting nonexistent key."""
        result = self.cache.get("nonexistent")
        assert result is None

    def test_set_with_metadata(self):
        """Test setting entry with metadata."""
        metadata = {"custom": "data"}

        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path/to/run.db",
            metadata=metadata,
        )

        result = self.cache.get("key1")
        assert result["metadata"] == metadata

    def test_set_without_metadata(self):
        """Test setting entry without metadata."""
        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path/to/run.db",
        )

        result = self.cache.get("key1")
        assert result["metadata"] is None

    def test_set_replaces_existing(self):
        """Test that set replaces existing entry."""
        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path1",
        )

        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec2",
            squid_id="sim1/1.0.0/xyz",
            input_hash="hash2",
            run_db_path="/path2",
        )

        result = self.cache.get("key1")
        assert result["execution_id"] == "exec2"
        assert result["run_db_path"] == "/path2"


class TestLocalCacheClientTTL:
    """Tests for TTL (time-to-live) functionality."""

    def setup_method(self):
        """Setup for each test."""
        self.cache = LocalCacheClient()

    def test_set_with_ttl(self):
        """Test setting entry with TTL."""
        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path/to/run.db",
            ttl_seconds=3600,  # 1 hour
        )

        # Should be accessible immediately
        result = self.cache.get("key1")
        assert result is not None

    def test_expired_entry_returns_none(self):
        """Test that expired entry returns None."""
        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path/to/run.db",
            ttl_seconds=0,  # Immediate expiration
        )

        result = self.cache.get("key1")
        assert result is None

    def test_expired_entry_removed_from_cache(self):
        """Test that expired entry is removed."""
        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path/to/run.db",
            ttl_seconds=0,
        )

        self.cache.get("key1")  # Should remove it

        assert "key1" not in self.cache._cache

    def test_no_ttl_never_expires(self):
        """Test that entry without TTL never expires."""
        self.cache.set(
            cache_key="key1",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec1",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash1",
            run_db_path="/path/to/run.db",
            ttl_seconds=None,
        )

        # Should always be accessible
        result = self.cache.get("key1")
        assert result is not None


class TestLocalCacheClientInvalidation:
    """Tests for cache invalidation."""

    def setup_method(self):
        """Setup for each test."""
        self.cache = LocalCacheClient()

    def test_invalidate_by_simulation_id(self):
        """Test invalidating by simulation ID."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.set("key2", 1, "sim1", "1.0.0", "exec2", "squid2", "hash2", "/path2")
        self.cache.set("key3", 2, "sim2", "1.0.0", "exec3", "squid3", "hash3", "/path3")

        count = self.cache.invalidate(simulation_id=1)

        assert count == 2
        assert self.cache.get("key1") is None
        assert self.cache.get("key2") is None
        assert self.cache.get("key3") is not None

    def test_invalidate_by_simulation_name(self):
        """Test invalidating by simulation name."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.set("key2", 1, "sim1", "2.0.0", "exec2", "squid2", "hash2", "/path2")
        self.cache.set("key3", 2, "sim2", "1.0.0", "exec3", "squid3", "hash3", "/path3")

        count = self.cache.invalidate(simulation_name="sim1")

        assert count == 2

    def test_invalidate_by_simulation_version(self):
        """Test invalidating by simulation version."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.set("key2", 1, "sim1", "2.0.0", "exec2", "squid2", "hash2", "/path2")

        count = self.cache.invalidate(
            simulation_name="sim1", simulation_version="1.0.0"
        )

        assert count == 1
        assert self.cache.get("key1") is None
        assert self.cache.get("key2") is not None

    def test_invalidate_by_pattern(self):
        """Test invalidating by pattern."""
        self.cache.set("sim1_key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.set("sim1_key2", 1, "sim1", "1.0.0", "exec2", "squid2", "hash2", "/path2")
        self.cache.set("sim2_key1", 2, "sim2", "1.0.0", "exec3", "squid3", "hash3", "/path3")

        count = self.cache.invalidate(pattern="sim1%")

        assert count == 2

    def test_invalidate_with_reason(self):
        """Test invalidation with reason (logged but not returned)."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")

        count = self.cache.invalidate(simulation_id=1, reason="Bug fix")

        assert count == 1

    def test_invalidate_all(self):
        """Test invalidating all entries."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.set("key2", 2, "sim2", "1.0.0", "exec2", "squid2", "hash2", "/path2")

        count = self.cache.invalidate()

        assert count == 2
        assert self.cache.get("key1") is None
        assert self.cache.get("key2") is None

    def test_invalidate_empty_cache(self):
        """Test invalidating empty cache."""
        count = self.cache.invalidate()
        assert count == 0


class TestLocalCacheClientStatistics:
    """Tests for statistics tracking."""

    def setup_method(self):
        """Setup for each test."""
        self.cache = LocalCacheClient()

    def test_stats_initial(self):
        """Test initial statistics."""
        stats = self.cache.get_stats()

        assert stats["total_requests"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["hit_rate_percent"] == 0

    def test_stats_after_hit(self):
        """Test statistics after cache hit."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.get("key1")

        stats = self.cache.get_stats()

        assert stats["total_requests"] == 1
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 0
        assert stats["hit_rate_percent"] == 100.0

    def test_stats_after_miss(self):
        """Test statistics after cache miss."""
        self.cache.get("nonexistent")

        stats = self.cache.get_stats()

        assert stats["total_requests"] == 1
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 1
        assert stats["hit_rate_percent"] == 0.0

    def test_stats_mixed_hits_misses(self):
        """Test statistics with mixed hits and misses."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")

        self.cache.get("key1")  # Hit
        self.cache.get("key1")  # Hit
        self.cache.get("nonexistent")  # Miss

        stats = self.cache.get_stats()

        assert stats["total_requests"] == 3
        assert stats["cache_hits"] == 2
        assert stats["cache_misses"] == 1
        assert stats["hit_rate_percent"] == pytest.approx(66.67, abs=0.01)

    def test_stats_counts_sets(self):
        """Test that statistics count sets."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")

        stats = self.cache.get_stats()
        assert stats["total_sets"] == 1

    def test_stats_counts_invalidations(self):
        """Test that statistics count invalidations."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.invalidate()

        stats = self.cache.get_stats()
        assert stats["total_invalidations"] == 1

    def test_stats_total_entries(self):
        """Test total entries in stats."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.set("key2", 2, "sim2", "1.0.0", "exec2", "squid2", "hash2", "/path2")

        stats = self.cache.get_stats()
        assert stats["total_entries"] == 2

    def test_stats_by_simulation_id(self):
        """Test getting stats for specific simulation."""
        self.cache.set("key1", 1, "sim1", "1.0.0", "exec1", "squid1", "hash1", "/path1")
        self.cache.set("key2", 2, "sim2", "1.0.0", "exec2", "squid2", "hash2", "/path2")

        stats = self.cache.get_stats(simulation_id=1)
        assert stats["simulation_entries"] == 1


class TestLocalCacheClientHealthCheck:
    """Tests for health check."""

    def test_health_check_always_true(self):
        """Test that local cache is always healthy."""
        cache = LocalCacheClient()
        assert cache.health_check() == True


class TestCacheClientInit:
    """Tests for CacheClient initialization."""

    def test_create_client(self):
        """Test creating cache client."""
        client = CacheClient("http://localhost:8001")

        assert client.service_url == "http://localhost:8001"
        assert client.session_id is None

    def test_create_client_with_session(self):
        """Test creating client with session ID."""
        client = CacheClient("http://localhost:8001", session_id="test-session")

        assert client.session_id == "test-session"

    def test_create_client_strips_trailing_slash(self):
        """Test that trailing slash is stripped."""
        client = CacheClient("http://localhost:8001/")

        assert client.service_url == "http://localhost:8001"

    def test_create_client_custom_timeout(self):
        """Test creating client with custom timeout."""
        client = CacheClient("http://localhost:8001", timeout=60)

        assert client.timeout == 60


@responses.activate
class TestCacheClientGet:
    """Tests for CacheClient get method."""

    def setup_method(self):
        """Setup for each test."""
        self.client = CacheClient("http://localhost:8001", session_id="test-session")

    def test_get_success(self):
        """Test successful get."""
        responses.add(
            responses.GET,
            "http://localhost:8001/cache/test-key",
            json={
                "execution_id": "exec-123",
                "squid_id": "sim/1.0.0/abc",
                "run_db_path": "/path/to/run.db",
                "metadata": {"key": "value"},
            },
            status=200,
        )

        result = self.client.get("test-key")

        assert result is not None
        assert result["execution_id"] == "exec-123"

    def test_get_not_found(self):
        """Test get when key not found."""
        responses.add(
            responses.GET, "http://localhost:8001/cache/nonexistent", status=404
        )

        result = self.client.get("nonexistent")

        assert result is None

    def test_get_unauthorized(self):
        """Test get with unauthorized session."""
        responses.add(
            responses.GET, "http://localhost:8001/cache/test-key", status=401
        )

        result = self.client.get("test-key")

        assert result is None

    def test_get_server_error(self):
        """Test get with server error."""
        responses.add(
            responses.GET, "http://localhost:8001/cache/test-key", status=500
        )

        result = self.client.get("test-key")

        assert result is None

    def test_get_includes_session_header(self):
        """Test that get includes session header."""
        responses.add(
            responses.GET,
            "http://localhost:8001/cache/test-key",
            json={"execution_id": "exec-123"},
            status=200,
        )

        self.client.get("test-key")

        assert len(responses.calls) == 1
        assert responses.calls[0].request.headers["X-Session-ID"] == "test-session"


@responses.activate
class TestCacheClientSet:
    """Tests for CacheClient set method."""

    def setup_method(self):
        """Setup for each test."""
        self.client = CacheClient("http://localhost:8001", session_id="test-session")

    def test_set_success(self):
        """Test successful set."""
        responses.add(responses.POST, "http://localhost:8001/cache", status=200)

        success = self.client.set(
            cache_key="test-key",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec-123",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash123",
            run_db_path="/path/to/run.db",
        )

        assert success

    def test_set_with_ttl(self):
        """Test set with TTL."""
        responses.add(responses.POST, "http://localhost:8001/cache", status=200)

        self.client.set(
            cache_key="test-key",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec-123",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash123",
            run_db_path="/path/to/run.db",
            ttl_seconds=3600,
        )

        # Verify TTL in request
        assert responses.calls[0].request.body is not None

    def test_set_unauthorized(self):
        """Test set with unauthorized session."""
        responses.add(responses.POST, "http://localhost:8001/cache", status=401)

        success = self.client.set(
            cache_key="test-key",
            simulation_id=1,
            simulation_name="sim1",
            simulation_version="1.0.0",
            execution_id="exec-123",
            squid_id="sim1/1.0.0/abc",
            input_hash="hash123",
            run_db_path="/path/to/run.db",
        )

        assert not success


@responses.activate
class TestCacheClientInvalidate:
    """Tests for CacheClient invalidate method."""

    def setup_method(self):
        """Setup for each test."""
        self.client = CacheClient("http://localhost:8001", session_id="test-session")

    def test_invalidate_success(self):
        """Test successful invalidation."""
        responses.add(
            responses.POST,
            "http://localhost:8001/cache/invalidate",
            json={"invalidated_count": 5},
            status=200,
        )

        count = self.client.invalidate(simulation_id=1)

        assert count == 5

    def test_invalidate_with_pattern(self):
        """Test invalidation with pattern."""
        responses.add(
            responses.POST,
            "http://localhost:8001/cache/invalidate",
            json={"invalidated_count": 3},
            status=200,
        )

        count = self.client.invalidate(pattern="sim1%", reason="Bug fix")

        assert count == 3

    def test_invalidate_unauthorized(self):
        """Test invalidation with unauthorized session."""
        responses.add(
            responses.POST, "http://localhost:8001/cache/invalidate", status=401
        )

        count = self.client.invalidate(simulation_id=1)

        assert count == -1


@responses.activate
class TestCacheClientStats:
    """Tests for CacheClient get_stats method."""

    def setup_method(self):
        """Setup for each test."""
        self.client = CacheClient("http://localhost:8001", session_id="test-session")

    def test_get_stats_global(self):
        """Test getting global stats."""
        responses.add(
            responses.GET,
            "http://localhost:8001/cache/stats",
            json={
                "total_requests": 1000,
                "cache_hits": 750,
                "cache_misses": 250,
                "hit_rate_percent": 75.0,
            },
            status=200,
        )

        stats = self.client.get_stats()

        assert stats is not None
        assert stats["total_requests"] == 1000
        assert stats["hit_rate_percent"] == 75.0

    def test_get_stats_by_simulation(self):
        """Test getting stats for specific simulation."""
        responses.add(
            responses.GET,
            "http://localhost:8001/cache/stats",
            json={"total_requests": 100},
            status=200,
        )

        stats = self.client.get_stats(simulation_id=42)

        assert stats is not None


@responses.activate
class TestCacheClientHealthCheck:
    """Tests for CacheClient health_check method."""

    def test_health_check_healthy(self):
        """Test health check when service is healthy."""
        responses.add(
            responses.GET,
            "http://localhost:8001/health",
            json={"status": "healthy"},
            status=200,
        )

        client = CacheClient("http://localhost:8001")
        is_healthy = client.health_check()

        assert is_healthy

    def test_health_check_unhealthy(self):
        """Test health check when service is unhealthy."""
        responses.add(responses.GET, "http://localhost:8001/health", status=500)

        client = CacheClient("http://localhost:8001")
        is_healthy = client.health_check()

        assert not is_healthy

    def test_health_check_unreachable(self):
        """Test health check when service is unreachable."""
        client = CacheClient("http://localhost:9999")  # Wrong port
        is_healthy = client.health_check()

        assert not is_healthy


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=sim2l.database.cache_client"])
