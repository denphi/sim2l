# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Comprehensive unit tests for SessionManager.

Tests authentication, session management, and privilege checking with high coverage.
"""

import pytest
from datetime import datetime, timedelta

from sim2l.database.session_manager import (
    Session,
    SessionManager,
    get_session_manager,
    reset_session_manager,
)


class TestSession:
    """Tests for Session class."""

    def test_create_session(self):
        """Test creating a session."""
        session = Session(
            session_id="test-session-001",
            user_id=1,
            username="testuser",
            privileges=["read", "write"],
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        assert session.session_id == "test-session-001"
        assert session.user_id == 1
        assert session.username == "testuser"
        assert "read" in session.privileges
        assert "write" in session.privileges

    def test_session_is_valid(self):
        """Test session validity check."""
        # Valid session (future expiration)
        session = Session(
            session_id="valid",
            user_id=1,
            username="user",
            privileges=["read"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert session.is_valid()

        # Expired session
        expired_session = Session(
            session_id="expired",
            user_id=1,
            username="user",
            privileges=["read"],
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert not expired_session.is_valid()

    def test_session_has_privilege(self):
        """Test privilege checking."""
        session = Session(
            session_id="test",
            user_id=1,
            username="user",
            privileges=["read", "write"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        assert session.has_privilege("read")
        assert session.has_privilege("write")
        assert not session.has_privilege("admin")

    def test_session_admin_has_all_privileges(self):
        """Test that admin privilege grants all access."""
        session = Session(
            session_id="admin",
            user_id=1,
            username="admin",
            privileges=["admin"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        assert session.has_privilege("read")
        assert session.has_privilege("write")
        assert session.has_privilege("catalog_update")
        assert session.has_privilege("admin")
        assert session.has_privilege("anything")

    def test_session_update_activity(self):
        """Test updating session activity."""
        session = Session(
            session_id="test",
            user_id=1,
            username="user",
            privileges=["read"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        initial_activity = session.last_activity
        session.update_activity()

        assert session.last_activity >= initial_activity

    def test_session_to_dict(self):
        """Test converting session to dictionary."""
        session = Session(
            session_id="test",
            user_id=1,
            username="user",
            privileges=["read", "write"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
            metadata={"key": "value"},
        )

        session_dict = session.to_dict()

        assert session_dict["session_id"] == "test"
        assert session_dict["user_id"] == 1
        assert session_dict["username"] == "user"
        assert "read" in session_dict["privileges"]
        assert session_dict["metadata"] == {"key": "value"}


class TestSessionManagerUserManagement:
    """Tests for user management in SessionManager."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()

    def test_default_admin_user_exists(self):
        """Test that default admin user is created."""
        # Should be able to authenticate as admin
        session = self.manager.authenticate("admin", "admin")
        assert session.username == "admin"
        assert "admin" in session.privileges

    def test_create_user_basic(self):
        """Test creating a basic user."""
        user_id = self.manager.create_user("alice", "password123")

        assert user_id > 0
        assert user_id != 1  # Not the default admin

    def test_create_user_with_role(self):
        """Test creating user with specific role."""
        user_id = self.manager.create_user("bob", "password", role="developer")
        assert user_id > 0

        # Authenticate and check privileges
        session = self.manager.authenticate("bob", "password")
        assert "catalog_update" in session.privileges

    def test_create_user_with_email(self):
        """Test creating user with email."""
        user_id = self.manager.create_user(
            "charlie", "password", email="charlie@example.com"
        )
        assert user_id > 0

    def test_create_user_duplicate_username(self):
        """Test that duplicate username raises error."""
        self.manager.create_user("duplicate", "password")

        with pytest.raises(ValueError, match="already exists"):
            self.manager.create_user("duplicate", "password")

    def test_create_multiple_users(self):
        """Test creating multiple users."""
        user_ids = []
        for i in range(5):
            user_id = self.manager.create_user(f"user{i}", f"password{i}")
            user_ids.append(user_id)

        # All IDs should be unique
        assert len(set(user_ids)) == len(user_ids)

    def test_user_role_privileges(self):
        """Test privileges for different roles."""
        # User role
        self.manager.create_user("user", "pass", role="user")
        user_session = self.manager.authenticate("user", "pass")
        assert "read" in user_session.privileges
        assert "write" in user_session.privileges
        assert "catalog_update" not in user_session.privileges

        # Developer role
        self.manager.create_user("dev", "pass", role="developer")
        dev_session = self.manager.authenticate("dev", "pass")
        assert "catalog_update" in dev_session.privileges

        # Admin role
        self.manager.create_user("admin2", "pass", role="admin")
        admin_session = self.manager.authenticate("admin2", "pass")
        assert "admin" in admin_session.privileges


class TestSessionManagerAuthentication:
    """Tests for authentication in SessionManager."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()
        self.manager.create_user("testuser", "testpass", role="developer")

    def test_authenticate_success(self):
        """Test successful authentication."""
        session = self.manager.authenticate("testuser", "testpass")

        assert session is not None
        assert session.username == "testuser"
        assert session.session_id is not None
        assert session.is_valid()

    def test_authenticate_wrong_password(self):
        """Test authentication with wrong password."""
        with pytest.raises(ValueError, match="Invalid username or password"):
            self.manager.authenticate("testuser", "wrongpass")

    def test_authenticate_nonexistent_user(self):
        """Test authentication with nonexistent user."""
        with pytest.raises(ValueError, match="Invalid username or password"):
            self.manager.authenticate("nonexistent", "password")

    def test_authenticate_custom_ttl(self):
        """Test authentication with custom TTL."""
        session = self.manager.authenticate("testuser", "testpass", ttl_hours=1)

        # Session should expire in approximately 1 hour
        time_to_expire = (session.expires_at - datetime.utcnow()).total_seconds()
        assert 3500 < time_to_expire < 3700  # ~1 hour (accounting for test execution)

    def test_authenticate_creates_unique_session_ids(self):
        """Test that each authentication creates unique session ID."""
        session1 = self.manager.authenticate("testuser", "testpass")
        session2 = self.manager.authenticate("testuser", "testpass")

        assert session1.session_id != session2.session_id

    def test_password_hashing(self):
        """Test that passwords are hashed."""
        # Create user and verify we can't authenticate with hash
        self.manager.create_user("hashtest", "mypassword")

        # Should not be able to authenticate with the hash
        password_hash = self.manager._hash_password("mypassword")
        with pytest.raises(ValueError):
            self.manager.authenticate("hashtest", password_hash)


class TestSessionManagerSessionOperations:
    """Tests for session operations."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()
        self.manager.create_user("user", "pass")
        self.session = self.manager.authenticate("user", "pass")

    def test_get_session(self):
        """Test getting a session by ID."""
        retrieved = self.manager.get_session(self.session.session_id)

        assert retrieved is not None
        assert retrieved.session_id == self.session.session_id
        assert retrieved.username == self.session.username

    def test_get_nonexistent_session(self):
        """Test getting nonexistent session."""
        retrieved = self.manager.get_session("nonexistent-session-id")
        assert retrieved is None

    def test_get_session_updates_activity(self):
        """Test that getting session updates last activity."""
        initial_activity = self.session.last_activity

        retrieved = self.manager.get_session(self.session.session_id)

        assert retrieved.last_activity >= initial_activity

    def test_validate_session_valid(self):
        """Test validating a valid session."""
        is_valid = self.manager.validate_session(self.session.session_id)
        assert is_valid

    def test_validate_session_invalid(self):
        """Test validating invalid session."""
        is_valid = self.manager.validate_session("invalid-session-id")
        assert not is_valid

    def test_validate_expired_session(self):
        """Test validating expired session."""
        # Create session with 0 hour TTL
        expired_session = self.manager.authenticate("user", "pass", ttl_hours=0)

        is_valid = self.manager.validate_session(expired_session.session_id)
        assert not is_valid

    def test_get_expired_session_removes_it(self):
        """Test that getting expired session removes it."""
        expired_session = self.manager.authenticate("user", "pass", ttl_hours=0)

        # First get should return None and remove it
        retrieved = self.manager.get_session(expired_session.session_id)
        assert retrieved is None

        # Second get should also return None
        retrieved = self.manager.get_session(expired_session.session_id)
        assert retrieved is None

    def test_invalidate_session(self):
        """Test invalidating a session."""
        self.manager.invalidate_session(self.session.session_id)

        # Session should no longer be valid
        is_valid = self.manager.validate_session(self.session.session_id)
        assert not is_valid

    def test_invalidate_nonexistent_session(self):
        """Test invalidating nonexistent session (should not error)."""
        self.manager.invalidate_session("nonexistent")


class TestSessionManagerPrivilegeChecking:
    """Tests for privilege checking."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()
        self.manager.create_user("user", "pass", role="user")
        self.manager.create_user("dev", "pass", role="developer")
        # "admin" already exists as the default admin user (password: "admin")

        self.user_session = self.manager.authenticate("user", "pass")
        self.dev_session = self.manager.authenticate("dev", "pass")
        self.admin_session = self.manager.authenticate("admin", "admin")

    def test_check_privilege_read(self):
        """Test checking read privilege."""
        assert self.manager.check_privilege(self.user_session.session_id, "read")
        assert self.manager.check_privilege(self.dev_session.session_id, "read")
        assert self.manager.check_privilege(self.admin_session.session_id, "read")

    def test_check_privilege_write(self):
        """Test checking write privilege."""
        assert self.manager.check_privilege(self.user_session.session_id, "write")
        assert self.manager.check_privilege(self.dev_session.session_id, "write")
        assert self.manager.check_privilege(self.admin_session.session_id, "write")

    def test_check_privilege_catalog_update(self):
        """Test checking catalog_update privilege."""
        assert not self.manager.check_privilege(
            self.user_session.session_id, "catalog_update"
        )
        assert self.manager.check_privilege(
            self.dev_session.session_id, "catalog_update"
        )
        assert self.manager.check_privilege(
            self.admin_session.session_id, "catalog_update"
        )

    def test_check_privilege_run(self):
        """Developer and admin sessions can execute catalog runs."""
        assert not self.manager.check_privilege(self.user_session.session_id, "run")
        assert self.manager.check_privilege(self.dev_session.session_id, "run")
        assert self.manager.check_privilege(self.admin_session.session_id, "run")
        assert self.manager.check_privilege(self.dev_session.session_id, "execute")
        assert self.manager.check_privilege(self.admin_session.session_id, "execute")

    def test_check_privilege_admin(self):
        """Test checking admin privilege."""
        assert not self.manager.check_privilege(self.user_session.session_id, "admin")
        assert not self.manager.check_privilege(self.dev_session.session_id, "admin")
        assert self.manager.check_privilege(self.admin_session.session_id, "admin")

    def test_check_privilege_invalid_session(self):
        """Test checking privilege for invalid session."""
        assert not self.manager.check_privilege("invalid-session", "read")

    def test_check_privilege_expired_session(self):
        """Test checking privilege for expired session."""
        expired = self.manager.authenticate("user", "pass", ttl_hours=0)
        assert not self.manager.check_privilege(expired.session_id, "read")


class TestSessionManagerListOperations:
    """Tests for listing and querying sessions."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()
        self.manager.create_user("user1", "pass")
        self.manager.create_user("user2", "pass")

    def test_list_sessions_empty(self):
        """Test listing sessions when none exist."""
        sessions = self.manager.list_sessions()
        assert len(sessions) == 0

    def test_list_sessions_single(self):
        """Test listing single session."""
        self.manager.authenticate("user1", "pass")

        sessions = self.manager.list_sessions()
        assert len(sessions) == 1

    def test_list_sessions_multiple(self):
        """Test listing multiple sessions."""
        self.manager.authenticate("user1", "pass")
        self.manager.authenticate("user2", "pass")

        sessions = self.manager.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_excludes_expired(self):
        """Test that listing excludes expired sessions."""
        self.manager.authenticate("user1", "pass", ttl_hours=24)
        self.manager.authenticate("user2", "pass", ttl_hours=0)  # Expired

        sessions = self.manager.list_sessions()
        assert len(sessions) == 1

    def test_get_user_sessions(self):
        """Test getting sessions for specific user."""
        user_id = self.manager._username_to_id["user1"]

        # Create multiple sessions for user1
        self.manager.authenticate("user1", "pass")
        self.manager.authenticate("user1", "pass")

        user_sessions = self.manager.get_user_sessions(user_id)
        assert len(user_sessions) == 2

    def test_get_user_sessions_different_users(self):
        """Test getting sessions differentiates users."""
        user1_id = self.manager._username_to_id["user1"]
        user2_id = self.manager._username_to_id["user2"]

        self.manager.authenticate("user1", "pass")
        self.manager.authenticate("user2", "pass")

        user1_sessions = self.manager.get_user_sessions(user1_id)
        user2_sessions = self.manager.get_user_sessions(user2_id)

        assert len(user1_sessions) == 1
        assert len(user2_sessions) == 1


class TestSessionManagerCleanup:
    """Tests for cleanup operations."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()
        self.manager.create_user("user", "pass")

    def test_cleanup_expired_sessions_none(self):
        """Test cleanup when no expired sessions."""
        self.manager.authenticate("user", "pass", ttl_hours=24)

        count = self.manager.cleanup_expired_sessions()
        assert count == 0

    def test_cleanup_expired_sessions_removes_expired(self):
        """Test cleanup removes expired sessions."""
        # Create valid and expired sessions
        valid = self.manager.authenticate("user", "pass", ttl_hours=24)
        expired1 = self.manager.authenticate("user", "pass", ttl_hours=0)
        expired2 = self.manager.authenticate("user", "pass", ttl_hours=0)

        count = self.manager.cleanup_expired_sessions()
        assert count == 2

        # Valid session should still exist
        assert self.manager.validate_session(valid.session_id)

        # Expired sessions should be gone
        assert not self.manager.validate_session(expired1.session_id)
        assert not self.manager.validate_session(expired2.session_id)


class TestSessionManagerAnonymous:
    """Tests for anonymous session creation."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()

    def test_create_anonymous_session_default(self):
        """Test creating anonymous session with defaults."""
        session = self.manager.create_anonymous_session()

        assert session.username == "anonymous"
        assert session.user_id == 0
        assert "read" in session.privileges
        assert "write" in session.privileges

    def test_create_anonymous_session_custom_privileges(self):
        """Test creating anonymous session with custom privileges."""
        session = self.manager.create_anonymous_session(privileges=["read"])

        assert "read" in session.privileges
        assert "write" not in session.privileges

    def test_create_anonymous_session_custom_ttl(self):
        """Test creating anonymous session with custom TTL."""
        session = self.manager.create_anonymous_session(ttl_hours=1)

        time_to_expire = (session.expires_at - datetime.utcnow()).total_seconds()
        assert 3500 < time_to_expire < 3700  # ~1 hour

    def test_create_anonymous_session_metadata(self):
        """Test anonymous session has metadata."""
        session = self.manager.create_anonymous_session()

        assert session.metadata.get("anonymous") == True

    def test_create_multiple_anonymous_sessions(self):
        """Test creating multiple anonymous sessions."""
        session1 = self.manager.create_anonymous_session()
        session2 = self.manager.create_anonymous_session()

        # Should have different IDs
        assert session1.session_id != session2.session_id


class TestGlobalSessionManager:
    """Tests for global session manager functions."""

    def test_get_session_manager_singleton(self):
        """Test that get_session_manager returns singleton."""
        manager1 = get_session_manager()
        manager2 = get_session_manager()

        assert manager1 is manager2

    def test_reset_session_manager(self):
        """Test resetting global session manager."""
        manager1 = get_session_manager()

        reset_session_manager()

        manager2 = get_session_manager()

        assert manager1 is not manager2

    def test_reset_clears_sessions(self):
        """Test that reset clears all sessions."""
        manager = get_session_manager()
        manager.create_user("user", "pass")
        session = manager.authenticate("user", "pass")

        reset_session_manager()

        new_manager = get_session_manager()

        # Old session should not be valid in new manager
        assert not new_manager.validate_session(session.session_id)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def setup_method(self):
        """Setup for each test."""
        self.manager = SessionManager()

    def test_empty_username(self):
        """Test creating user with empty username."""
        # This should work (no explicit validation)
        user_id = self.manager.create_user("", "password")
        assert user_id > 0

    def test_empty_password(self):
        """Test creating user with empty password."""
        user_id = self.manager.create_user("user", "")
        assert user_id > 0

        # Should be able to authenticate with empty password
        session = self.manager.authenticate("user", "")
        assert session is not None

    def test_very_long_username(self):
        """Test creating user with very long username."""
        long_username = "a" * 1000
        user_id = self.manager.create_user(long_username, "pass")
        assert user_id > 0

    def test_special_characters_in_username(self):
        """Test username with special characters."""
        special_username = "user@example.com"
        user_id = self.manager.create_user(special_username, "pass")
        assert user_id > 0

        session = self.manager.authenticate(special_username, "pass")
        assert session.username == special_username

    def test_unicode_in_credentials(self):
        """Test unicode characters in username and password."""
        username = "用户名"
        password = "密码"

        user_id = self.manager.create_user(username, password)
        session = self.manager.authenticate(username, password)

        assert session.username == username

    def test_case_sensitive_passwords(self):
        """Test that passwords are case-sensitive."""
        self.manager.create_user("user", "Password123")

        # Correct case
        session = self.manager.authenticate("user", "Password123")
        assert session is not None

        # Wrong case
        with pytest.raises(ValueError):
            self.manager.authenticate("user", "password123")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=sim2l.database.session_manager"])
