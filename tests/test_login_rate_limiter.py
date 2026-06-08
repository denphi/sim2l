"""Tests for the per-(ip, username) login throttle (review item #T15)."""

import pytest

from sim2l.services._common import LoginRateLimiter


def test_allow_under_limit():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60.0)
    for _ in range(3):
        assert limiter.allow("1.2.3.4", "alice") is True


def test_blocks_when_limit_exceeded():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60.0)
    for _ in range(3):
        limiter.allow("1.2.3.4", "alice")
    assert limiter.allow("1.2.3.4", "alice") is False


def test_different_users_have_separate_buckets():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60.0)
    limiter.allow("1.2.3.4", "alice")
    limiter.allow("1.2.3.4", "alice")
    assert limiter.allow("1.2.3.4", "alice") is False
    # Bob from the same IP starts fresh.
    assert limiter.allow("1.2.3.4", "bob") is True


def test_different_ips_have_separate_buckets():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60.0)
    limiter.allow("1.2.3.4", "alice")
    limiter.allow("1.2.3.4", "alice")
    assert limiter.allow("1.2.3.4", "alice") is False
    assert limiter.allow("5.6.7.8", "alice") is True


def test_reset_clears_bucket():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60.0)
    limiter.allow("1.2.3.4", "alice")
    limiter.allow("1.2.3.4", "alice")
    assert limiter.allow("1.2.3.4", "alice") is False
    limiter.reset("1.2.3.4", "alice")
    assert limiter.allow("1.2.3.4", "alice") is True


def test_username_case_insensitive():
    # The bucket key lowercases the username so attackers can't trivially
    # bypass the limit by rotating the case.
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60.0)
    limiter.allow("1.2.3.4", "Alice")
    limiter.allow("1.2.3.4", "alice")
    assert limiter.allow("1.2.3.4", "ALICE") is False


def test_window_expiry(monkeypatch):
    # Move monotonic forward to simulate window expiry without sleeping.
    fake_time = {"now": 1000.0}

    def fake_monotonic():
        return fake_time["now"]

    monkeypatch.setattr("sim2l.services._common.time.monotonic", fake_monotonic)

    limiter = LoginRateLimiter(max_attempts=2, window_seconds=10.0)
    assert limiter.allow("1.2.3.4", "alice") is True
    assert limiter.allow("1.2.3.4", "alice") is True
    assert limiter.allow("1.2.3.4", "alice") is False
    fake_time["now"] += 11.0
    assert limiter.allow("1.2.3.4", "alice") is True
