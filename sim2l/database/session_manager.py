# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Session management for authentication and privilege checking.
"""

import uuid
import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


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

    def __init__(self, default_ttl_hours: int = 24):
        self.default_ttl_hours = default_ttl_hours
        self._sessions: Dict[str, Session] = {}
        self._users: Dict[int, Dict[str, Any]] = {}
        self._username_to_id: Dict[str, int] = {}
        self._next_user_id = 1

        # Create default admin user
        self._create_default_admin()

    def _create_default_admin(self):
        """Create default admin user for local development."""
        logger.warning(
            "Default admin user created with password 'admin'. "
            "Change this immediately in any non-development environment via create_user()."
        )
        admin_user = {
            "id": 1,
            "username": "admin",
            "password_hash": self._hash_password("admin"),
            "role": "admin",
            "email": "admin@localhost",
        }
        self._users[1] = admin_user
        self._username_to_id["admin"] = 1
        self._next_user_id = 2

    def _hash_password(self, password: str) -> bytes:
        """Hash a password using bcrypt with a random salt."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

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
        user_id = self._username_to_id.get(username)
        if user_id is None:
            raise ValueError("Invalid username or password")

        user = self._users[user_id]

        if not self._verify_password(password, user["password_hash"]):
            raise ValueError("Invalid username or password")

        # Determine privileges based on role
        role = user["role"]
        if role == "admin":
            privileges = ["admin", "read", "write", "catalog_update"]
        elif role == "developer":
            privileges = ["read", "write", "catalog_update"]
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
