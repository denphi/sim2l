from pathlib import Path

import pytest

import sim2l
from sim2l import SimulationDefinition, SimulationRepository
from sim2l.executor import LocalExecutor
from sim2l.schema import InputSchema, OutputSchema
from sim2l.database.catalog_client import _workflow_bundle_from_simulation


WORKFLOW_SOURCE = b"""
def simulate(x=1.0):
    return {"y": x + 1}
"""

GLOBAL_OFFSET = 2


def workflow_with_global(x=1.0):
    return {"y": x + GLOBAL_OFFSET}


def test_function_workflow_loads_from_source_after_deploy(tmp_path):
    db_path = tmp_path / "repo.db"
    sim2l.configure(db_path=db_path)
    repo = SimulationRepository(db_path=db_path)
    sim = SimulationDefinition(
        name="source_function",
        version="0.1.0",
        inputs=InputSchema.from_yaml("x:\n  type: Number\n  default: 1.0\n"),
        outputs=OutputSchema.from_yaml("y:\n  type: Number\n"),
        workflow=WORKFLOW_SOURCE,
        workflow_type="function",
    )

    repo.deploy(sim)
    loaded = repo.load("source_function", "0.1.0")
    result = loaded.run(x=2.0, executor=LocalExecutor(cache=False))

    assert result.status == "completed"
    assert result.outputs.y == pytest.approx(3.0)


def test_function_workflow_bytes_execute_without_pickle(tmp_path):
    db_path = tmp_path / "repo.db"
    sim2l.configure(db_path=db_path)
    SimulationRepository.create(db_path)
    sim = SimulationDefinition(
        name="source_bytes",
        version="0.1.0",
        inputs=InputSchema.from_yaml("x:\n  type: Number\n  default: 1.0\n"),
        outputs=OutputSchema.from_yaml("y:\n  type: Number\n"),
        workflow=WORKFLOW_SOURCE,
        workflow_type="function",
    )

    result = sim.run(x=4.0, executor=LocalExecutor(cache=False))

    assert result.status == "completed"
    assert result.outputs.y == pytest.approx(5.0)


def test_callable_workflow_bundle_rejects_global_dependencies():
    sim = SimulationDefinition.from_function(
        workflow_with_global,
        name="global_dep",
        version="0.1.0",
        inputs=InputSchema.from_yaml("x:\n  type: Number\n  default: 1.0\n"),
        outputs=OutputSchema.from_yaml("y:\n  type: Number\n"),
    )

    with pytest.raises(ValueError, match="not self-contained"):
        _workflow_bundle_from_simulation(sim)
