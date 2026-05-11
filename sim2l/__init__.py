# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
sim2l - Simulation Framework with Database-Backed Persistence

A modular, notebook-agnostic library for defining, deploying, and executing
simulations as versioned, reusable artifacts.
"""

from .version import __version__

# Schema and type system
from .schema import (
    Field,
    Schema,
    InputSchema,
    OutputSchema,
    Integer,
    Number,
    Text,
    Array,
    Image,
    Element,
    List,
    Dict,
    Boolean,
    register_field_type,
    get_field_class,
)

# Definition
from .definition import (
    SimulationDefinition,
    SimulationMetadata,
)

# Repository
from .repository import (
    SimulationRepository,
    load_simulation,
    list_simulations,
)

# Configuration
from .config import configure, get_config

# High-level API
from .api import (
    deploy_simulation,
    get_inputs,
    save_outputs,
)

# Utilities
from .utils import (
    compute_squid_id,
    get_squid_id_for_parameters,
)

# Executors
from .executor import (
    Executor,
    IsolatedFunctionExecutor,
    LocalExecutor,
    NotebookExecutor,
)

# Results
from .result import (
    ExecutionResult,
    load_result,
)

__all__ = [
    # Version
    "__version__",

    # Schema
    "Field",
    "Schema",
    "InputSchema",
    "OutputSchema",
    "Integer",
    "Number",
    "Text",
    "Array",
    "Image",
    "Element",
    "List",
    "Dict",
    "Boolean",
    "register_field_type",
    "get_field_class",

    # Definition
    "SimulationDefinition",
    "SimulationMetadata",

    # Repository
    "SimulationRepository",
    "load_simulation",
    "list_simulations",

    # Configuration
    "configure",
    "get_config",

    # API
    "deploy_simulation",
    "get_inputs",
    "save_outputs",

    # Utilities
    "compute_squid_id",
    "get_squid_id_for_parameters",

    # Executors
    "Executor",
    "IsolatedFunctionExecutor",
    "LocalExecutor",
    "NotebookExecutor",

    # Results
    "ExecutionResult",
    "load_result",
]
