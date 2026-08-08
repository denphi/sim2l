# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Session management for authentication and privilege checking.
"""

# Keep `X | None` annotations evaluatable on Python 3.8/3.9 (see requires-python).
from __future__ import annotations

import os
import secrets
import uuid
import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


def _is_dev_mode() -> bool:
    """Return True when the process is started in dev/test mode."""
    return os.environ.get("SIM2L_DEV_MODE", "").lower() in {"1", "true", "yes", "on"}


def _admin_password_file() -> "pathlib.Path":
    """Path to the persistent random admin password file.

    Shared across services so all three (cache / catalog / results) agree on
    the same admin credential, instead of generating three different
    one-shot random passwords (review item #S8).
    """
    import pathlib

    base = pathlib.Path(os.environ.get("SIM2L_HOME", str(pathlib.Path.home() / ".sim2l")))
    return base / "admin_password"


def _read_persisted_admin_password() -> Optional[str]:
    """Return the persisted admin password from disk, or None if absent."""
    path = _admin_password_file()
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except (FileNotFoundError, PermissionError):
        return None
    except OSError as exc:
        logger.warning("Could not read admin password file %s: %s", path, exc)
        return None


def _persist_admin_password(password: str) -> tuple["Optional[pathlib.Path]", str]:
    """Atomically claim the admin-password file with this password.

    Returns ``(path, persisted_password)``. When two service processes start
    concurrently and both call this function, only the first ``O_EXCL`` open
    wins. The losing caller reads the existing file and reports back the
    winner's password — so all services end up agreeing on a single
    credential. Review items #S7 and #T3.
    """
    import pathlib

    path = _admin_password_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create admin password file dir %s: %s", path, exc)
        return None, password

    # O_CREAT | O_EXCL: succeed only if we create the file. If it already
    # exists (race or prior run), fall back to reading whatever the winner
    # wrote.
    try:
        fd = os.open(
            str(path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        try:
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return path, existing
        except OSError as exc:
            logger.warning("Could not read existing admin password file %s: %s", path, exc)
        # Neither create-fresh nor read-existing worked; fall through.
        return None, password
    except OSError as exc:
        logger.warning("Could not write admin password file %s: %s", path, exc)
        return None, password

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(password)
    except OSError as exc:
        logger.warning("Failed writing admin password file %s: %s", path, exc)
        return None, password

    # Belt-and-suspenders chmod in case the umask widened the perms.
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        pass
    return path, password


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (DB-compatible)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Session:
    """Represents a user session with privileges."""

    def __init__(
        self,
        session_id: str,
        user_id: int,
        username: str,
        privileges: List[str],
        expires_at: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.username = username
        self.privileges = set(privileges)
        self.expires_at = expires_at
        self.metadata = metadata or {}
        self.created_at = _utcnow()
        self.last_activity = _utcnow()

    def is_valid(self) -> bool:
        """Check if session is still valid."""
        return _utcnow() < self.expires_at

    def has_privilege(self, privilege: str) -> bool:
        """Check if session has a specific privilege."""
        return privilege in self.privileges or "admin" in self.privileges

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = _utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "username": self.username,
            "privileges": list(self.privileges),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "metadata": self.metadata,
        }


class SessionManager:
    """
    Manages user sessions for authentication and authorization.

    This is a simple in-memory implementation for local use.
    For production, this should connect to the master catalog database
    or a dedicated session service (Redis, etc.).
    """

    def __init__(self, default_ttl_hours: int = 24, *, dev_mode: Optional[bool] = None):
        self.default_ttl_hours = default_ttl_hours
        # dev_mode=None means "honour the SIM2L_DEV_MODE env var"; pass True/False
        # explicitly to override the env (used by tests).
        self._dev_mode = _is_dev_mode() if dev_mode is None else dev_mode
        self._sessions: Dict[str, Session] = {}
        self._users: Dict[int, Dict[str, Any]] = {}
        self._username_to_id: Dict[str, int] = {}
        self._next_user_id = 1
        # Built on first use by _dummy_hash(); keeps authenticate() constant-cost
        # for unknown usernames without paying a bcrypt round on construction.
        self._dummy_password_hash: Optional[bytes] = None
        # Cheap counter so session creation amortises expiry cleanup.
        self._logins_since_sweep = 0

        # Create default admin user (password chosen by environment/dev-mode)
        self._create_default_admin()

    def _resolve_admin_password(self) -> tuple[Optional[str], str]:
        """Pick the admin password and report the source.

        Returns ``(password, source)`` where ``source`` is one of:
          - ``"env"``     – ``SIM2L_ADMIN_PASSWORD`` env var
          - ``"file"``    – persisted file under ``~/.sim2l/admin_password``
          - ``"dev"``     – dev-mode literal ``"admin"``
          - ``"random"``  – caller must generate and persist

        Resolution order:
        1. ``SIM2L_ADMIN_PASSWORD`` env var (explicit operator override).
        2. Persisted password file (shared across services — review #S8).
        3. Dev mode literal ``"admin"``.
        4. Otherwise: caller generates a new random password and persists it.
        """
        explicit = os.environ.get("SIM2L_ADMIN_PASSWORD")
        if explicit:
            return explicit, "env"
        persisted = _read_persisted_admin_password()
        if persisted:
            return persisted, "file"
        if self._dev_mode:
            return "admin", "dev"
        return None, "random"

    def _create_default_admin(self):
        """Create the default admin user.

        Production deployments without ``SIM2L_ADMIN_PASSWORD`` get a random
        password written to ``~/.sim2l/admin_password`` (0600). The
        credential is NOT logged — review item #S7. Subsequent service
        startups reuse the file so all three services (cache / catalog /
        results) agree on the same admin (#S8).
        """
        password, source = self._resolve_admin_password()
        if password is None:
            # Generate a candidate; the actual persisted password may differ
            # if another service raced us and wrote first (review #T3).
            candidate = secrets.token_urlsafe(24)
            path, password = _persist_admin_password(candidate)
            if path is not None:
                logger.warning(
                    "Default admin user created with random password. "
                    "Read it from %s (mode 0600). Set SIM2L_ADMIN_PASSWORD "
                    "to override, or SIM2L_DEV_MODE=true for the literal "
                    "'admin' (development only).",
                    path,
                )
            else:
                # Persistence failed (read-only HOME, permission error). Fall
                # back to a one-shot log so the operator can still recover —
                # this is now the unusual case rather than the default.
                logger.warning(
                    "Default admin user created with random password (could "
                    "not persist to disk). Password: %r. Set "
                    "SIM2L_ADMIN_PASSWORD next time to control this.",
                    password,
                )
            source = "random"
        elif source == "dev":
            logger.warning(
                "Default admin user created with password 'admin' (dev mode). "
                "DO NOT use this configuration outside development."
            )
        elif source == "file":
            logger.info(
                "Default admin user loaded from persisted password file %s.",
                _admin_password_file(),
            )
        elif source == "env":
            logger.info(
                "Default admin user created with password from SIM2L_ADMIN_PASSWORD."
            )
        admin_user = {
            "id": 1,
            "username": "admin",
            "password_hash": self._hash_password(password),
            "role": "admin",
            "email": "admin@localhost",
        }
        self._users[1] = admin_user
        self._username_to_id["admin"] = 1
        self._next_user_id = 2

    def _hash_password(self, password: str) -> bytes:
        """Hash a password using bcrypt with a random salt."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    def _dummy_hash(self) -> bytes:
        """A throwaway bcrypt hash to verify against when the user is unknown.

        Computed once, lazily, at the same cost factor as a real hash, so
        :meth:`authenticate` performs identical work whether or not the username
        exists. See the comment there for why that matters.
        """
        if self._dummy_password_hash is None:
            self._dummy_password_hash = self._hash_password(secrets.token_urlsafe(32))
        return self._dummy_password_hash

    def _verify_password(self, password: str, hashed) -> bool:
        """Verify a password against a bcrypt hash."""
        if isinstance(hashed, str):
            hashed = hashed.encode("utf-8")
        if isinstance(password, bytes):
            # Reject non-string passwords to avoid bcrypt misuse
            return False
        return bcrypt.checkpw(password.encode("utf-8"), hashed)

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "user",
        email: Optional[str] = None,
    ) -> int:
        """Create a new user."""
        if username in self._username_to_id:
            raise ValueError(f"User {username} already exists")

        user_id = self._next_user_id
        self._next_user_id += 1

        user = {
            "id": user_id,
            "username": username,
            "password_hash": self._hash_password(password),
            "role": role,
            "email": email,
            "created_at": _utcnow(),
        }

        self._users[user_id] = user
        self._username_to_id[username] = user_id

        logger.info(f"Created user {username} (ID: {user_id}, Role: {role})")
        return user_id

    def authenticate(
        self, username: str, password: str, ttl_hours: Optional[int] = None
    ) -> Session:
        """
        Authenticate a user and create a session.

        Args:
            username: Username
            password: Password
            ttl_hours: Session TTL in hours (default: 24)

        Returns:
            Session object

        Raises:
            ValueError: If authentication fails
        """
        # Always run one bcrypt verify, whether or not the username exists.
        #
        # Returning early on an unknown user leaked which usernames are real:
        # bcrypt's cost factor — the thing protecting the password — made the
        # two paths trivially distinguishable (measured 203 ms for an existing
        # user versus 0.000 ms for an unknown one). The error message was
        # already identical; the timing was not. Verifying against a throwaway
        # hash costs the same as the real check and closes the oracle.
        user_id = self._username_to_id.get(username)
        user = self._users.get(user_id) if user_id is not None else None
        expected_hash = user["password_hash"] if user else self._dummy_hash()
        password_ok = self._verify_password(password, expected_hash)

        if user is None or not password_ok:
            raise ValueError("Invalid username or password")

        # Determine privileges based on role
        role = user["role"]
        if role == "admin":
            privileges = ["admin", "read", "write", "catalog_update", "execute", "run"]
        elif role == "developer":
            privileges = ["read", "write", "catalog_update", "execute", "run"]
        else:
            privileges = ["read", "write"]

        # Create session
        session_id = str(uuid.uuid4())
        ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        expires_at = _utcnow() + timedelta(hours=ttl)

        session = Session(
            session_id=session_id,
            user_id=user_id,
            username=username,
            privileges=privileges,
            expires_at=expires_at,
        )

        self._sessions[session_id] = session

        # Amortise expiry cleanup onto session creation. cleanup_expired_sessions
        # was correct but its only non-test caller was list_sessions(), and
        # get_session() only evicts a session someone happens to look up — so
        # sessions never touched again (an abandoned login, the common case) were
        # retained for the process lifetime.
        self._logins_since_sweep += 1
        if self._logins_since_sweep >= 64:
            self._logins_since_sweep = 0
            self.cleanup_expired_sessions()

        logger.info(
            f"User {username} authenticated (Session: {session_id[:8]}..., "
            f"Expires: {expires_at.isoformat()})"
        )

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        if not session.is_valid():
            logger.warning(f"Session {session_id[:8]}... has expired")
            del self._sessions[session_id]
            return None

        session.update_activity()
        return session

    def validate_session(self, session_id: str) -> bool:
        """Check if a session ID is valid."""
        return self.get_session(session_id) is not None

    def check_privilege(self, session_id: str, privilege: str) -> bool:
        """
        Check if a session has a specific privilege.

        Args:
            session_id: Session ID
            privilege: Required privilege ('read', 'write', 'catalog_update', 'admin')

        Returns:
            True if session has the privilege, False otherwise
        """
        session = self.get_session(session_id)
        if session is None:
            return False

        return session.has_privilege(privilege)

    def refresh_session(self, session_id: str, ttl_hours: Optional[int] = None) -> bool:
        """Extend a session's expiry by the configured TTL.

        Returns True if the session was found and refreshed, False otherwise.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        if not session.is_valid():
            del self._sessions[session_id]
            return False

        ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        session.expires_at = _utcnow() + timedelta(hours=ttl)
        session.update_activity()
        logger.info(
            f"Session {session_id[:8]}... refreshed, new expiry: {session.expires_at.isoformat()}"
        )
        return True

    def invalidate_session(self, session_id: str):
        """Invalidate a session."""
        if session_id in self._sessions:
            username = self._sessions[session_id].username
            del self._sessions[session_id]
            logger.info(f"Session {session_id[:8]}... invalidated for user {username}")

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        expired = [
            sid for sid, session in self._sessions.items() if not session.is_valid()
        ]

        for sid in expired:
            del self._sessions[sid]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")

        return len(expired)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions."""
        self.cleanup_expired_sessions()
        return [session.to_dict() for session in self._sessions.values()]

    def get_user_sessions(self, user_id: int) -> List[Session]:
        """Get all sessions for a user."""
        return [s for s in self._sessions.values() if s.user_id == user_id]

    def create_anonymous_session(
        self, privileges: Optional[List[str]] = None, ttl_hours: Optional[int] = None
    ) -> Session:
        """
        Create an anonymous session for local development.

        Args:
            privileges: List of privileges (default: ['read', 'write'])
            ttl_hours: Session TTL in hours (default: 24)

        Returns:
            Session object
        """
        session_id = str(uuid.uuid4())
        ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        expires_at = _utcnow() + timedelta(hours=ttl)
        privileges = privileges or ["read", "write"]

        session = Session(
            session_id=session_id,
            user_id=0,
            username="anonymous",
            privileges=privileges,
            expires_at=expires_at,
            metadata={"anonymous": True},
        )

        self._sessions[session_id] = session

        logger.info(
            f"Created anonymous session {session_id[:8]}... "
            f"with privileges {privileges}"
        )

        return session


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def reset_session_manager():
    """Reset the global session manager (for testing)."""
    global _session_manager
    _session_manager = None
