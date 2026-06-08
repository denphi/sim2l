# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Shared helpers for sim2l Flask microservices.

The three services (`cache_service`, `catalog_service`, `results_service`)
historically copy-pasted the same boilerplate: header-reading auth, per-thread
SQLite/PostgreSQL connection pools, deprecated `datetime.utcnow()` patches,
and a near-identical PostgreSQL-to-SQLite schema adapter. This module is the
beginnings of a consolidated base; callers gradually migrate to it.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, Optional, Tuple


# ── Time helpers ─────────────────────────────────────────────────────────────


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (DB-comparison-safe).

    Avoids the deprecated `datetime.utcnow()` while keeping naive output so
    downstream SQLite comparisons against `datetime('now')` (which is naive
    UTC) behave correctly.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Login rate limiter ───────────────────────────────────────────────────────


class LoginRateLimiter:
    """In-process sliding-window limiter keyed by (ip, username).

    Review item #T15: ``/session/login`` previously accepted unlimited
    credential guesses. Adding a per-(ip, username) limiter takes the
    online-brute-force vector off the table without needing an external
    Redis. Configuration is intentionally generous (5 attempts / 60s) so
    legitimate users hitting "Login" three times in quick succession
    aren't locked out.

    The limiter is process-local — services scaled horizontally would need
    a shared store. That's a known limitation; the limiter is still useful
    for single-process and single-replica deployments, which is what the
    dev-loop targets.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: float = 60.0):
        self.max_attempts = max_attempts
        self.window_seconds = float(window_seconds)
        self._buckets: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, ip: Optional[str], username: Optional[str]) -> Tuple[str, str]:
        return (ip or "unknown", (username or "").lower())

    def allow(self, ip: Optional[str], username: Optional[str]) -> bool:
        """Return True when the request is under the limit, False otherwise.

        Each call records a timestamp regardless of outcome — limiting on
        attempt rate (rather than failures only) means a sustained guess
        spree still gets rejected even if the attacker rotates usernames.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        key = self._key(ip, username)
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                return False
            bucket.append(now)
            return True

    def reset(self, ip: Optional[str] = None, username: Optional[str] = None) -> None:
        """Clear a bucket — used by tests and on successful logins."""
        with self._lock:
            if ip is None and username is None:
                self._buckets.clear()
            else:
                self._buckets.pop(self._key(ip, username), None)


def client_ip(request) -> str:
    """Best-effort client IP from a Flask request.

    Prefers ``X-Forwarded-For`` (first hop) so deployments behind a known
    reverse proxy get the real client; falls back to ``remote_addr``.
    Operators who don't trust the header should strip it at the proxy.
    """
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


# ── Auth header parsing ──────────────────────────────────────────────────────


def extract_session_id(
    request,
    *,
    require_auth: bool,
    demo_session: str = "demo-session",
) -> tuple[Optional[str], Optional[tuple[dict, int]]]:
    """Read the X-Session-ID header and apply the standard auth fallback.

    Returns `(session_id, None)` on success, or `(None, (body, status))` on
    failure — the caller should `return jsonify(body), status` directly.

    When `require_auth=False`, a missing header falls back to `demo_session`
    so dev-mode services keep working without explicit credentials.
    """
    session_id = request.headers.get("X-Session-ID")
    if require_auth and not session_id:
        return None, ({"error": "Missing session ID"}, 401)
    return session_id or demo_session, None


# ── PostgreSQL-to-SQLite schema adapter ──────────────────────────────────────


# Default type substitutions applied to PG schemas before running them on
# SQLite. Order matters: BIGSERIAL must be matched before BIGINT, etc.
_DEFAULT_TYPE_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("BIGINT", "INTEGER"),
    ("JSONB", "TEXT"),
    ("BOOLEAN", "INTEGER"),
    ("DEFAULT true", "DEFAULT 1"),
    ("DEFAULT false", "DEFAULT 0"),
)

# PG-specific block starters that must be stripped wholesale. A block runs
# from one of these lines through either a closing `$$;` pair (for functions)
# or the next semicolon outside `$$` (for views/triggers).
DEFAULT_PG_BLOCK_STARTERS: tuple[str, ...] = (
    "CREATE OR REPLACE FUNCTION",
    "CREATE OR REPLACE VIEW",
)


def adapt_postgres_schema_for_sqlite(
    schema_sql: str,
    *,
    pg_block_starters: Iterable[str] = DEFAULT_PG_BLOCK_STARTERS,
    extra_substitutions: Iterable[tuple[str, str]] = (),
    extra_regex_substitutions: Iterable[tuple[str, str]] = (),
    restore_if_not_exists_prefix: Optional[str] = None,
) -> str:
    """Convert PostgreSQL schema SQL into SQLite-compatible SQL.

    Behaviour matches what `cache_service` and `catalog_service` previously
    open-coded:

    1. Apply type substitutions (BIGSERIAL→INTEGER PK AUTOINCREMENT, etc.).
    2. Strip every PG-only block (functions/views/triggers).
    3. Drop `IF NOT EXISTS` so subsequent `executescript` works, then restore
       it on `CREATE TABLE` so reruns don't fail.

    Args:
        schema_sql: Raw PG schema source.
        pg_block_starters: Strings whose presence on a line starts a block
            that should be skipped until the closing `$$;` (functions) or
            terminating `;` (views/triggers).
        extra_substitutions: Extra `(old, new)` string replacements applied
            after the defaults (e.g., service-specific quirks).
        extra_regex_substitutions: Same but as `(pattern, repl)` for
            `re.sub` (e.g., dropping `USING GIN(...)` index clauses).
        restore_if_not_exists_prefix: If set, restore `CREATE TABLE IF NOT
            EXISTS <prefix>` on tables matching that prefix only. If `None`,
            restore on every `CREATE TABLE` line. Use `""` to be explicit.
    """
    import re

    # 1. Type substitutions
    for old, new in _DEFAULT_TYPE_SUBSTITUTIONS:
        schema_sql = schema_sql.replace(old, new)
    for old, new in extra_substitutions:
        schema_sql = schema_sql.replace(old, new)
    for pattern, repl in extra_regex_substitutions:
        schema_sql = re.sub(pattern, repl, schema_sql)

    # Tear off CREATE TABLE IF NOT EXISTS uniformly — we restore selectively
    # at the end so callers can control which tables get the marker.
    schema_sql = schema_sql.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")

    # 2. Strip PG-only blocks
    starters = tuple(pg_block_starters)
    filtered_lines: list[str] = []
    skip_until_end = False
    paren_depth = 0
    for line in schema_sql.split("\n"):
        if any(starter in line for starter in starters):
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
        if stripped:
            filtered_lines.append(line)

    schema_sql = "\n".join(filtered_lines)

    # 3. Restore IF NOT EXISTS on CREATE TABLE (selective or universal)
    if restore_if_not_exists_prefix is None:
        schema_sql = schema_sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
    else:
        schema_sql = schema_sql.replace(
            f"CREATE TABLE {restore_if_not_exists_prefix}",
            f"CREATE TABLE IF NOT EXISTS {restore_if_not_exists_prefix}",
        )

    return schema_sql
