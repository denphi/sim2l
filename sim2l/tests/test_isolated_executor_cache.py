"""Cache-service wiring for ``IsolatedFunctionExecutor``.

The isolated executor is arc's default runner. Before these hooks it had
no cache integration at all: identical inputs always re-ran the subprocess,
and the cache service stayed empty. These tests pin the lookup/store flow
so future refactors don't quietly remove it.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sim2l.executor.isolated import IsolatedFunctionExecutor


class _StubSim:
    name = "demo"
    version = "0.1.0"

    class _Inputs:
        @staticmethod
        def validate(d):
            return d

    inputs = _Inputs()


def test_check_cache_returns_none_when_no_cache_service(monkeypatch):
    """No cache_service_url ⇒ check_cache is a no-op (legacy behavior)."""
    monkeypatch.setattr(
        "sim2l.executor.isolated.get_config",
        lambda: SimpleNamespace(cache_service_url=None),
        raising=False,
    )
    # If get_config isn't yet imported at module level, attribute may not exist.
    # Patch on the source module too.
    import sim2l.config as cfg
    monkeypatch.setattr(cfg, "get_config", lambda: SimpleNamespace(cache_service_url=None))

    ex = IsolatedFunctionExecutor(cache=True)
    assert ex.check_cache(_StubSim(), {"x": 1}) is None


def test_check_cache_hits_cache_service_when_configured(monkeypatch):
    """With a configured cache service, check_cache fetches by SQUID id."""
    import sim2l.config as cfg
    monkeypatch.setattr(
        cfg, "get_config",
        lambda: SimpleNamespace(
            cache_service_url="http://localhost:8001",
            cache_session_id="cs-1",
        ),
    )

    cache_client = MagicMock()
    cache_client.get.return_value = {"execution_id": "exec-abc"}

    import sim2l.database as db_mod
    monkeypatch.setattr(db_mod, "CacheClient", lambda **kw: cache_client)

    # the (fallback-capable) loader must return a sentinel
    fake_result = SimpleNamespace(execution_id="exec-abc")
    import sim2l.result as result_mod
    monkeypatch.setattr(result_mod, "load_result_with_fallback", lambda eid: fake_result)

    ex = IsolatedFunctionExecutor(cache=True)
    out = ex.check_cache(_StubSim(), {"x": 1})
    assert out is fake_result
    cache_client.get.assert_called_once()
    # The returned result is stamped so consumers (arc adapter, registries)
    # can distinguish a cache hit from a fresh execution.
    assert out.cache_hit is True


def test_check_cache_treats_lookup_failure_as_miss(monkeypatch):
    """Cache service raising must not propagate — log + miss."""
    import sim2l.config as cfg
    monkeypatch.setattr(
        cfg, "get_config",
        lambda: SimpleNamespace(
            cache_service_url="http://localhost:8001",
            cache_session_id=None,
        ),
    )

    class _Boom:
        def get(self, *a, **kw):
            raise RuntimeError("network down")

    import sim2l.database as db_mod
    monkeypatch.setattr(db_mod, "CacheClient", lambda **kw: _Boom())

    ex = IsolatedFunctionExecutor(cache=True)
    assert ex.check_cache(_StubSim(), {"x": 1}) is None


def test_check_cache_returns_none_when_cache_disabled(monkeypatch):
    """cache=False shortcuts before touching config."""
    ex = IsolatedFunctionExecutor(cache=False)
    assert ex.check_cache(_StubSim(), {"x": 1}) is None


def test_store_cache_service_posts_set_with_squid_key(monkeypatch):
    """After a completed run, the result lands in the cache service."""
    import sim2l.config as cfg
    monkeypatch.setattr(
        cfg, "get_config",
        lambda: SimpleNamespace(
            cache_service_url="http://localhost:8001",
            cache_session_id="cs-1",
        ),
    )

    cache_client = MagicMock()
    cache_client.set.return_value = True

    import sim2l.database as db_mod
    monkeypatch.setattr(db_mod, "CacheClient", lambda **kw: cache_client)

    result = SimpleNamespace(
        execution_id="exec-1",
        squid_id="sq-deadbeef",
        simulation_id=42,
        simulation_name="demo",
        simulation_version="0.1.0",
        duration_seconds=0.25,
        status="completed",
    )
    ex = IsolatedFunctionExecutor(cache=True)
    ex._store_cache_service(result, {"thickness": 5.0})

    cache_client.set.assert_called_once()
    kwargs = cache_client.set.call_args.kwargs
    assert kwargs["cache_key"] == "sq-deadbeef"
    assert kwargs["execution_id"] == "exec-1"
    assert kwargs["simulation_id"] == 42
    # input_hash is deterministic from inputs — just check it's a hex digest
    assert len(kwargs["input_hash"]) == 64


def test_store_cache_service_swallows_errors(monkeypatch):
    """Cache persistence failures must never break the execution."""
    import sim2l.config as cfg
    monkeypatch.setattr(
        cfg, "get_config",
        lambda: SimpleNamespace(cache_service_url="http://localhost:8001"),
    )

    class _Boom:
        def set(self, **kw):
            raise RuntimeError("server down")

    import sim2l.database as db_mod
    monkeypatch.setattr(db_mod, "CacheClient", lambda **kw: _Boom())

    result = SimpleNamespace(
        execution_id="e", squid_id="s", simulation_id=1,
        simulation_name="n", simulation_version="v",
        duration_seconds=0.0, status="completed",
    )
    ex = IsolatedFunctionExecutor(cache=True)
    # Must not raise.
    ex._store_cache_service(result, {})


def test_store_cache_service_skipped_when_unconfigured(monkeypatch):
    """No cache_service_url ⇒ store is a no-op (no client constructed)."""
    import sim2l.config as cfg
    monkeypatch.setattr(
        cfg, "get_config", lambda: SimpleNamespace(cache_service_url=None)
    )

    import sim2l.database as db_mod
    def _no(*a, **kw):
        pytest.fail("CacheClient must not be constructed when unconfigured")
    monkeypatch.setattr(db_mod, "CacheClient", _no)

    result = SimpleNamespace(
        execution_id="e", squid_id="s", simulation_id=1,
        simulation_name="n", simulation_version="v",
        duration_seconds=0.0, status="completed",
    )
    ex = IsolatedFunctionExecutor(cache=True)
    ex._store_cache_service(result, {})


def test_load_result_with_fallback_uses_results_service(monkeypatch):
    """A cache hit produced on another installation has no local DB row —
    the loader reconstructs the result from the results service."""
    import sim2l.config as cfg
    from sim2l.result import result as result_mod

    monkeypatch.setattr(
        cfg, "get_config",
        lambda: SimpleNamespace(
            results_service_url="http://localhost:8003",
            results_session_id="rs-1",
        ),
    )
    # also patch the module-level import used inside result.py
    import sim2l.result.result as rr
    monkeypatch.setattr(
        rr, "load_result",
        lambda eid, db_path=None: (_ for _ in ()).throw(ValueError("no local row")),
    )

    service_row = {
        "execution_id": "exec-remote",
        "simulation_name": "demo",
        "simulation_version": "0.1.0",
        "squid_id": "sq-remote",
        "input_params": {"x": 1.0},
        "output_params": {"y": 2.0, "label": "ok"},
        "status": "completed",
        "duration_seconds": 0.7,
    }

    client = MagicMock()
    client.get_result.return_value = service_row
    import sim2l.database.results_client as rc_mod
    monkeypatch.setattr(rc_mod, "ResultsClient", lambda **kw: client)

    out = rr.load_result_with_fallback("exec-remote")
    assert out.execution_id == "exec-remote"
    assert out.simulation_name == "demo"
    assert out.outputs.y == 2.0
    assert out.outputs.label == "ok"
    assert out.status == "completed"
    assert out.executor_type == "results-service"


def test_load_result_with_fallback_reraises_without_service(monkeypatch):
    """No results service configured → the local error propagates."""
    import sim2l.config as cfg
    import sim2l.result.result as rr

    monkeypatch.setattr(cfg, "get_config", lambda: SimpleNamespace())
    monkeypatch.setattr(
        rr, "load_result",
        lambda eid, db_path=None: (_ for _ in ()).throw(ValueError("no local row")),
    )
    with pytest.raises(ValueError, match="no local row"):
        rr.load_result_with_fallback("exec-x")
