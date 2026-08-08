# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Authentication and authorization guarantees for the sim2l services.

Each test here pins a control that was previously present but not effective:
a rate limiter keyed on a value the client chooses, a constant-time error
message in front of a very non-constant-time code path, and a privilege model
the destructive endpoints did not consult on every backend.
"""

import os
import statistics
import time
from types import SimpleNamespace

import pytest

from sim2l.services._common import LoginRateLimiter, client_ip


def _request(xff=None, addr="203.0.113.9"):
    return SimpleNamespace(
        headers={"X-Forwarded-For": xff} if xff else {},
        remote_addr=addr,
    )


# ── client identity ──────────────────────────────────────────────────────────


def test_x_forwarded_for_is_ignored_from_an_untrusted_peer(monkeypatch):
    """The limiter must key on something the client cannot choose.

    ``X-Forwarded-For`` was honoured unconditionally, so rotating it put every
    request in a fresh bucket: 200 of 200 credential guesses were accepted where
    a fixed address got 5 of 20.
    """
    monkeypatch.delenv("SIM2L_TRUSTED_PROXIES", raising=False)
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=60.0)

    allowed = sum(
        limiter.allow(client_ip(_request(xff=f"10.0.0.{i}")), "admin")
        for i in range(200)
    )

    assert allowed == 5, f"rotating X-Forwarded-For bypassed the limiter ({allowed} allowed)"


def test_x_forwarded_for_is_honoured_from_a_trusted_proxy(monkeypatch):
    """Behind a declared proxy the header is the real client, so use it."""
    monkeypatch.setenv("SIM2L_TRUSTED_PROXIES", "203.0.113.9")
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=60.0)

    # Distinct real clients each get their own budget…
    assert all(
        limiter.allow(client_ip(_request(xff=f"10.0.0.{i}")), "admin")
        for i in range(20)
    )
    # …and one of them still gets throttled on its own.
    allowed = sum(
        limiter.allow(client_ip(_request(xff="10.0.0.99")), "admin")
        for _ in range(20)
    )
    assert allowed == 5


def test_trusted_proxy_uses_rightmost_untrusted_hop(monkeypatch):
    """Only hops our own proxies appended are trustworthy."""
    monkeypatch.setenv("SIM2L_TRUSTED_PROXIES", "203.0.113.9,10.1.1.1")
    # A client that forges a chain cannot make us read its leftmost entry.
    assert client_ip(_request(xff="1.2.3.4, 198.51.100.7, 10.1.1.1")) == "198.51.100.7"


# ── limiter memory ───────────────────────────────────────────────────────────


def test_rate_limiter_does_not_grow_without_bound():
    """Bucket count must track rate × window, not total requests ever seen.

    The map was a defaultdict that never dropped a key: 50,001 entries after
    50,000 addresses, driven from an unauthenticated endpoint.
    """
    counts = []
    for total in (20_000, 80_000):
        limiter = LoginRateLimiter(max_attempts=5, window_seconds=0.01, sweep_every=64)
        for i in range(total):
            limiter.allow(f"10.{i >> 16 & 255}.{i >> 8 & 255}.{i & 255}", "admin")
        counts.append(len(limiter._buckets))

    small, large = counts
    assert large < small * 2, (
        f"bucket count scaled with request volume ({small} -> {large}); "
        "expired buckets are not being reclaimed"
    )


def test_rate_limiter_reclaims_after_the_window_elapses():
    limiter = LoginRateLimiter(max_attempts=5, window_seconds=0.01, sweep_every=8)
    for i in range(500):
        limiter.allow(f"10.0.{i >> 8 & 255}.{i & 255}", "admin")

    time.sleep(0.05)
    for _ in range(16):  # trigger at least one sweep
        limiter.allow("10.9.9.9", "admin")

    assert len(limiter._buckets) < 10


# ── credential timing ────────────────────────────────────────────────────────


@pytest.mark.usefixtures("_dev_mode_session_manager")
def test_authentication_timing_does_not_reveal_valid_usernames(session_manager):
    """Both outcomes must cost the same.

    ``authenticate`` returned before bcrypt for an unknown user — 203 ms versus
    0.000 ms — so the cost factor protecting the password advertised which
    usernames exist.
    """
    def median_ms(username, runs=7):
        samples = []
        for _ in range(runs):
            started = time.perf_counter()
            with pytest.raises(ValueError):
                session_manager.authenticate(username, "definitely-wrong")
            samples.append((time.perf_counter() - started) * 1000)
        return statistics.median(samples)

    existing = median_ms("admin")
    unknown = median_ms("no-such-user-here")

    assert unknown > 1.0, "unknown-user path skipped the hash entirely"
    ratio = max(existing, unknown) / max(min(existing, unknown), 1e-9)
    assert ratio < 3.0, (
        f"timing still distinguishes valid usernames "
        f"(existing {existing:.1f} ms vs unknown {unknown:.1f} ms, {ratio:.1f}x)"
    )


def test_authentication_still_rejects_both_cases(session_manager):
    """Closing the oracle must not have made either path succeed."""
    with pytest.raises(ValueError, match="Invalid username or password"):
        session_manager.authenticate("admin", "wrong-password")
    with pytest.raises(ValueError, match="Invalid username or password"):
        session_manager.authenticate("no-such-user", "wrong-password")


def test_valid_credentials_still_authenticate(session_manager):
    session = session_manager.authenticate("admin", "admin")
    assert session.username == "admin"
    assert "admin" in session.privileges


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def _dev_mode_session_manager():
    return None


@pytest.fixture
def session_manager(monkeypatch, tmp_path):
    """A SessionManager with the dev-mode 'admin' password.

    SIM2L_HOME is redirected at a tmpdir so a persisted admin_password on the
    developer's machine cannot outrank the dev-mode literal.
    """
    monkeypatch.setenv("SIM2L_HOME", str(tmp_path))
    monkeypatch.delenv("SIM2L_ADMIN_PASSWORD", raising=False)
    from sim2l.database.session_manager import SessionManager

    return SessionManager(dev_mode=True)


# ── destructive-endpoint authorization ───────────────────────────────────────


def test_sqlite_cache_backend_requires_write_for_delete_all(tmp_path):
    """Clear-all must demand write/admin on SQLite as it does on PostgreSQL.

    The two backends disagreed, and SQLite — the default in start_services.sh
    and the Docker images — accepted any valid session, so a read/write user
    could wipe the whole cache.
    """
    from sim2l.services.cache_service import SQLiteCacheBackend

    backend = SQLiteCacheBackend(str(tmp_path / "cache.db"))
    assert hasattr(backend, "_check_write_session"), (
        "SQLiteCacheBackend still lacks the write check its PostgreSQL "
        "counterpart enforces"
    )

    conn = backend._get_conn()
    conn.execute(
        "INSERT INTO cache_sessions (session_id, user_id, expires_at, access_level, is_valid)"
        " VALUES (?, ?, datetime('now', '+1 hour'), ?, 1)",
        ("read-only-session", 7, "read"),
    )
    conn.execute(
        "INSERT INTO cache_sessions (session_id, user_id, expires_at, access_level, is_valid)"
        " VALUES (?, ?, datetime('now', '+1 hour'), ?, 1)",
        ("writer-session", 8, "write"),
    )
    conn.commit()

    assert backend._check_session("read-only-session") is True   # valid…
    assert backend._check_write_session("read-only-session") is False  # …but read-only

    with pytest.raises(PermissionError):
        backend.delete_all("read-only-session")

    backend.delete_all("writer-session")  # write access succeeds


def test_both_cache_backends_guard_delete_all_identically():
    """The guard must not depend on which backend the service was started with."""
    import ast
    import inspect

    from sim2l.services import cache_service

    source = inspect.getsource(cache_service)
    tree = ast.parse(source)
    guards = {}
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for node in cls.body:
            if isinstance(node, ast.FunctionDef) and node.name == "delete_all":
                calls = [
                    c.func.attr for c in ast.walk(node)
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                ]
                guards[cls.name] = next((c for c in calls if "check" in c), None)

    assert set(guards.values()) == {"_check_write_session"}, (
        f"delete_all is guarded differently per backend: {guards}"
    )
