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

import os
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

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 60.0,
        sweep_every: int = 256,
    ):
        self.max_attempts = max_attempts
        self.window_seconds = float(window_seconds)
        self._buckets: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._sweep_every = max(1, int(sweep_every))
        self._calls_since_sweep = 0

    def _key(self, ip: Optional[str], username: Optional[str]) -> Tuple[str, str]:
        return (ip or "unknown", (username or "").lower())

    def allow(self, ip: Optional[str], username: Optional[str]) -> bool:
        """Return True when the request is under the limit, False otherwise.

        Each call records a timestamp regardless of outcome — limiting on
        attempt rate (rather than failures only) means a sustained guess
        spree still gets rejected even if the attacker rotates usernames.

        Buckets that fall empty are dropped, and every so often the whole map is
        swept. Without that the ``defaultdict`` grew one permanent entry per
        distinct (ip, username) ever seen — 50,001 retained after 50,000
        addresses in a 60 ms window — which is unbounded memory driven from an
        unauthenticated endpoint.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        key = self._key(ip, username)
        with self._lock:
            self._maybe_sweep(cutoff)
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                return False
            bucket.append(now)
            return True

    def _maybe_sweep(self, cutoff: float) -> None:
        """Drop fully-expired buckets. Caller must hold ``self._lock``.

        Amortised: a full pass every ``_sweep_every`` calls keeps this O(1) per
        request on average, and the map can only hold keys seen within roughly
        the last window plus one sweep interval.
        """
        self._calls_since_sweep += 1
        if self._calls_since_sweep < self._sweep_every:
            return
        self._calls_since_sweep = 0
        stale = [
            key for key, bucket in self._buckets.items()
            if not bucket or bucket[-1] < cutoff
        ]
        for key in stale:
            del self._buckets[key]

    def reset(self, ip: Optional[str] = None, username: Optional[str] = None) -> None:
        """Clear a bucket — used by tests and on successful logins."""
        with self._lock:
            if ip is None and username is None:
                self._buckets.clear()
            else:
                self._buckets.pop(self._key(ip, username), None)


def _trusted_proxies() -> frozenset:
    """Peer addresses whose ``X-Forwarded-For`` we believe.

    Read from ``SIM2L_TRUSTED_PROXIES`` (comma-separated). Empty by default:
    the bundled ``start_services.sh`` and Docker compose put nothing in front of
    these services, so with no configuration there is no proxy to trust.
    """
    raw = os.environ.get("SIM2L_TRUSTED_PROXIES", "")
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def client_ip(request) -> str:
    """Identify the client for rate limiting.

    ``X-Forwarded-For`` is honoured **only** when the immediate peer is listed in
    ``SIM2L_TRUSTED_PROXIES``; otherwise the header is attacker-controlled and
    the peer address is the only trustworthy identity.

    This used to prefer the header unconditionally, which handed anyone a way to
    opt out of :class:`LoginRateLimiter` entirely: a fresh
    ``X-Forwarded-For`` per request lands in a fresh bucket, so the limiter added
    for review item #T15 allowed unlimited credential guesses (measured: 200 of
    200 attempts accepted while rotating the header, versus 5 of 20 from a fixed
    address). Rate limiting is only meaningful when keyed on something the
    client cannot choose.
    """
    peer = request.remote_addr or "unknown"
    trusted = _trusted_proxies()
    if peer in trusted:
        fwd = request.headers.get("X-Forwarded-For")
        if fwd:
            # Right-most untrusted hop: walk from the end past our own proxies.
            hops = [h.strip() for h in fwd.split(",") if h.strip()]
            for hop in reversed(hops):
                if hop not in trusted:
                    return hop
    return peer


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


# ── Serving ──────────────────────────────────────────────────────────────────


def serve_app(app, host: str, port: int, service_name: str) -> None:
    """Serve a service app on a production WSGI server when one is available.

    All three services ended in ``app.run(...)``, and the Docker images invoke
    exactly that — so the Flask *development* server was the production server.
    Werkzeug's own documentation says not to do this: no worker recycling, no
    graceful restart, no request limits, and a debug-oriented error path.

    Waitress is used when installed (pure Python, so it needs no toolchain in a
    slim image and behaves the same on macOS/Windows for local development).
    Without it we fall back to ``app.run`` and say so loudly rather than failing
    to start — a developer who has not installed the prod extras should still be
    able to run the service.

    ``threads`` is set explicitly rather than inherited: the executors these
    services call are themselves process-spawning and the notebook path
    serializes on an environment lock, so a very wide thread pool buys little.
    """
    threads = int(os.environ.get("SIM2L_SERVER_THREADS", "8"))
    try:
        from waitress import serve as _waitress_serve
    except ImportError:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(
            "waitress is not installed — falling back to the Flask development "
            "server for %s. This is fine for local development and unsuitable "
            "for deployment; install it with `pip install waitress` (it is in "
            "requirements/prod.txt).",
            service_name,
        )
        app.run(host=host, port=port, debug=False)
        return

    __import__("logging").getLogger(__name__).info(
        "Serving %s on http://%s:%s via waitress (%d threads)",
        service_name, host, port, threads,
    )
    _waitress_serve(app, host=host, port=port, threads=threads)


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
