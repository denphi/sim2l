# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Concurrency guarantees for the notebook executor's environment window.

The Flask services run threaded (``Flask.run`` defaults ``threaded=True``), so
two ``/simulations/<id>/execute`` requests for notebook workflows overlap in one
process. Per-run identity reaches the notebook through process-global
environment variables that the spawned kernel inherits, and
``sim2l.api.save_outputs`` reads ``SIM2L_EXECUTION_ID`` from inside that kernel
to decide which execution its outputs belong to.

Before ``_execution_environment`` existed, overlapping runs overwrote each
other's values between the set and the kernel spawn: outputs were written under
whichever id happened to be current. It failed silently — no exception, and the
stored data looks perfectly well-formed, so a misfiled result is undetectable
after the fact. That is the specific failure these tests exist to prevent.

They deliberately do not run Papermill. The contract under test is "what does
the environment look like at the moment the kernel would be spawned", which is
exactly what the context manager owns.
"""

import os
import threading

import pytest

from sim2l.executor.notebook import _execution_environment, _notebook_timeouts


def test_execution_environment_isolates_concurrent_runs():
    """Each run must observe its own id at kernel-spawn time."""
    observed = {}
    barrier = threading.Barrier(8)

    def run(execution_id):
        barrier.wait()  # maximise overlap
        with _execution_environment({
            "SIM2L_EXECUTION_ID": execution_id,
            "SIM2L_DB_PATH": f"/tmp/{execution_id}.db",
        }):
            # Stand-in for pm.execute_notebook: the kernel inherits os.environ
            # here, so this read is what save_outputs() would see.
            observed[execution_id] = os.environ.get("SIM2L_EXECUTION_ID")

    threads = [threading.Thread(target=run, args=(f"run-{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    misattributed = {run_id: seen for run_id, seen in observed.items() if run_id != seen}
    assert not misattributed, (
        "notebook runs observed another run's execution id at spawn time — "
        f"their outputs would be recorded against the wrong execution: {misattributed}"
    )


def test_execution_environment_restores_after_failure():
    """A raising notebook must not leave its identity set for the next run."""
    os.environ.pop("SIM2L_EXECUTION_ID", None)

    with pytest.raises(RuntimeError):
        with _execution_environment({"SIM2L_EXECUTION_ID": "run-that-fails"}):
            raise RuntimeError("notebook cell raised")

    assert os.environ.get("SIM2L_EXECUTION_ID") is None, (
        "a failed execution leaked SIM2L_EXECUTION_ID; the next run's outputs "
        "could be attributed to it"
    )


def test_execution_environment_restores_preexisting_values(monkeypatch):
    """Restore the caller's prior value rather than deleting the variable."""
    monkeypatch.setenv("SIM2L_DB_PATH", "/original/path.db")

    with _execution_environment({"SIM2L_DB_PATH": "/run/scoped.db"}):
        assert os.environ["SIM2L_DB_PATH"] == "/run/scoped.db"

    assert os.environ["SIM2L_DB_PATH"] == "/original/path.db"


def test_notebook_execution_is_bounded_by_default(monkeypatch):
    """Notebook runs get a timeout, like the function executor already had."""
    monkeypatch.delenv("SIM2L_NOTEBOOK_EXEC_TIMEOUT", raising=False)
    monkeypatch.delenv("SIM2L_NOTEBOOK_START_TIMEOUT", raising=False)

    timeouts = _notebook_timeouts()
    assert timeouts["execution_timeout"] == 3600.0
    assert timeouts["start_timeout"] == 60.0


@pytest.mark.parametrize(
    "value,expected",
    [("120", 120.0), ("0", None), ("-1", None), ("not-a-number", 3600.0)],
)
def test_notebook_timeout_env_override(monkeypatch, value, expected):
    """0/negative means explicitly unbounded; garbage falls back to the default.

    Unbounded has to stay reachable — this library exists to run solves that
    legitimately take hours.
    """
    monkeypatch.setenv("SIM2L_NOTEBOOK_EXEC_TIMEOUT", value)
    assert _notebook_timeouts()["execution_timeout"] == expected


def test_papermill_accepts_the_timeout_kwargs_we_pass():
    """Guard the kwarg names against a Papermill upgrade renaming them.

    ``execution_timeout`` is not a parameter of ``execute_notebook`` itself; it
    rides through ``**engine_kwargs`` into the engine, which maps it onto
    nbclient's ``timeout`` trait. A rename there would silently un-bound every
    notebook run rather than raising.
    """
    import inspect

    from papermill.engines import NBClientEngine

    params = inspect.signature(NBClientEngine.execute_managed_notebook).parameters
    assert "execution_timeout" in params
    assert "start_timeout" in params
