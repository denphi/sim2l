# sim2l Reference Implementation Structure

## Directory Layout

```
sim2l/
├── setup.py
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── docs/
│   ├── architecture.md
│   ├── getting_started.md
│   ├── api_reference.md
│   ├── migration_guide.md
│   └── examples/
│       ├── authoring_notebook.ipynb
│       ├── consumer_notebook.ipynb
│       └── advanced_workflows.ipynb
├── sim2l/
│   ├── __init__.py                 # Public API exports
│   ├── version.py
│   ├── config.py                   # Global configuration
│   │
│   ├── schema/                     # Type system and validation
│   │   ├── __init__.py
│   │   ├── field.py                # Base Field class
│   │   ├── types.py                # Integer, Number, Text, Array, etc.
│   │   ├── schema.py               # Schema container class
│   │   ├── validation.py           # Cross-field validation logic
│   │   └── registry.py             # Field type registration
│   │
│   ├── definition/                 # Simulation definition
│   │   ├── __init__.py
│   │   ├── simulation.py           # SimulationDefinition class
│   │   ├── parser.py               # Parse from notebooks/YAML
│   │   ├── workflow.py             # WorkflowSpec class
│   │   └── metadata.py             # Metadata handling
│   │
│   ├── repository/                 # Persistence layer
│   │   ├── __init__.py
│   │   ├── repository.py           # SimulationRepository class
│   │   ├── backend.py              # StorageBackend abstract base
│   │   ├── sqlite.py               # SQLiteBackend implementation
│   │   ├── models.py               # ORM-like data models
│   │   ├── schema.sql              # Database schema DDL
│   │   └── migrations/             # Database migrations
│   │       └── 001_initial.sql
│   │
│   ├── executor/                   # Execution engine
│   │   ├── __init__.py
│   │   ├── base.py                 # Executor abstract base
│   │   ├── local.py                # LocalExecutor
│   │   ├── notebook.py             # NotebookExecutor (Papermill)
│   │   ├── submit.py               # SubmitExecutor (HUB)
│   │   ├── context.py              # ExecutionContext
│   │   └── cache.py                # Caching logic
│   │
│   ├── result/                     # Result management
│   │   ├── __init__.py
│   │   ├── result.py               # ExecutionResult class
│   │   ├── outputs.py              # OutputData accessor
│   │   ├── artifacts.py            # ArtifactStore for large files
│   │   └── serialization.py        # Serialize/deserialize outputs
│   │
│   ├── workflow/                   # Workflow orchestration (future)
│   │   ├── __init__.py
│   │   ├── graph.py                # WorkflowGraph (DAG)
│   │   ├── step.py                 # Step node
│   │   └── executor.py             # Workflow executor
│   │
│   ├── migration/                  # Migration tools
│   │   ├── __init__.py
│   │   ├── converter.py            # Convert simtool notebooks
│   │   ├── importer.py             # Import simtool cache data
│   │   └── compat.py               # Backward compatibility shim
│   │
│   ├── cli/                        # Command line interface
│   │   ├── __init__.py
│   │   ├── main.py                 # CLI entry point
│   │   ├── commands/
│   │   │   ├── deploy.py
│   │   │   ├── run.py
│   │   │   ├── list.py
│   │   │   ├── info.py
│   │   │   └── migrate.py
│   │   └── utils.py
│   │
│   ├── notebook/                   # Jupyter integration
│   │   ├── __init__.py
│   │   ├── magics.py               # IPython magics (%%sim2l_inputs, etc.)
│   │   ├── introspection.py        # Notebook introspection utilities
│   │   └── display.py              # Rich display helpers
│   │
│   └── utils/                      # Shared utilities
│       ├── __init__.py
│       ├── hash.py                 # Hashing for cache keys
│       ├── serialization.py        # JSON/pickle utilities
│       ├── units.py                # Pint unit registry wrapper
│       └── logging.py              # Logging configuration
│
└── tests/
    ├── __init__.py
    ├── conftest.py                 # Pytest fixtures
    ├── test_schema/
    │   ├── test_field.py
    │   ├── test_types.py
    │   └── test_validation.py
    ├── test_definition/
    │   ├── test_simulation.py
    │   └── test_parser.py
    ├── test_repository/
    │   ├── test_repository.py
    │   ├── test_sqlite.py
    │   └── test_cache.py
    ├── test_executor/
    │   ├── test_local.py
    │   ├── test_notebook.py
    │   └── test_context.py
    ├── test_result/
    │   └── test_result.py
    ├── test_migration/
    │   └── test_converter.py
    ├── fixtures/
    │   ├── sample_notebook.ipynb
    │   ├── inputs.yaml
    │   └── outputs.yaml
    └── integration/
        └── test_end_to_end.py
```

---

## Core Module Code Examples

### `sim2l/__init__.py` - Public API

```python
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
    Integer,
    Number,
    Text,
    Array,
    Image,
    Element,
    List,
    Dict,
    Boolean,
)

# Definition
from .definition import (
    SimulationDefinition,
    InputSchema,
    OutputSchema,
)

# Repository
from .repository import (
    SimulationRepository,
    load_simulation,
    list_simulations,
)

# Execution
from .executor import (
    Executor,
    LocalExecutor,
    NotebookExecutor,
    SubmitExecutor,
)

# Results
from .result import (
    ExecutionResult,
    load_result,
)

# High-level API functions
from .api import (
    deploy_simulation,
    run_simulation,
    get_inputs,
    save_outputs,
)

# Migration
from .migration import (
    migrate_notebook,
    import_simtool_cache,
)

# Configuration
from .config import configure, get_config

__all__ = [
    # Version
    "__version__",

    # Schema
    "Field",
    "Schema",
    "Integer",
    "Number",
    "Text",
    "Array",
    "Image",
    "Element",
    "List",
    "Dict",
    "Boolean",

    # Definition
    "SimulationDefinition",
    "InputSchema",
    "OutputSchema",

    # Repository
    "SimulationRepository",
    "load_simulation",
    "list_simulations",

    # Execution
    "Executor",
    "LocalExecutor",
    "NotebookExecutor",
    "SubmitExecutor",

    # Results
    "ExecutionResult",
    "load_result",

    # API
    "deploy_simulation",
    "run_simulation",
    "get_inputs",
    "save_outputs",

    # Migration
    "migrate_notebook",
    "import_simtool_cache",

    # Configuration
    "configure",
    "get_config",
]
```

---

### `sim2l/config.py` - Global Configuration

```python
"""Global configuration management"""

import os
from pathlib import Path
from typing import Optional
import json

class Config:
    """Global sim2l configuration"""

    def __init__(self):
        self.db_path = self._default_db_path()
        self.cache_enabled = True
        self.default_executor = "local"
        self.artifact_storage = "database"  # or "filesystem"
        self.artifact_base_path = None
        self.log_level = "INFO"

    def _default_db_path(self) -> Path:
        """Default database location"""
        home = Path.home()
        sim2l_dir = home / ".sim2l"
        sim2l_dir.mkdir(exist_ok=True)
        return sim2l_dir / "simulations.db"

    def load_from_file(self, config_path: Path):
        """Load configuration from JSON file"""
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)

    def save_to_file(self, config_path: Path):
        """Save configuration to JSON file"""
        data = {
            "db_path": str(self.db_path),
            "cache_enabled": self.cache_enabled,
            "default_executor": self.default_executor,
            "artifact_storage": self.artifact_storage,
            "log_level": self.log_level,
        }
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)

# Global config instance
_config = Config()

# Try to load from user config
_user_config = Path.home() / ".sim2l" / "config.json"
if _user_config.exists():
    _config.load_from_file(_user_config)

def get_config() -> Config:
    """Get global configuration"""
    return _config

def configure(**kwargs):
    """Update global configuration

    Args:
        db_path: Path to simulation database
        cache_enabled: Enable/disable caching
        default_executor: Default executor type
        artifact_storage: "database" or "filesystem"
        log_level: Logging level
    """
    for key, value in kwargs.items():
        if hasattr(_config, key):
            setattr(_config, key, value)
        else:
            raise ValueError(f"Unknown configuration option: {key}")
```

---

### `sim2l/schema/field.py` - Base Field Class

```python
"""Base Field class for type system"""

from typing import Any, Optional, Union
from abc import ABC, abstractmethod

class Field(ABC):
    """Base class for all parameter field types"""

    def __init__(
        self,
        *,
        default: Any = None,
        optional: bool = False,
        description: str = "",
        metadata: Optional[dict] = None,
        required_if: Optional[str] = None,
    ):
        """Initialize field

        Args:
            default: Default value
            optional: Whether field is optional
            description: Human-readable description
            metadata: Additional metadata
            required_if: Conditional requirement expression
        """
        self.default = default
        self.optional = optional
        self.description = description
        self.metadata = metadata or {}
        self.required_if = required_if
        self._value = None

    @property
    def value(self):
        """Get field value"""
        if self._value is None:
            return self.default
        return self._value

    @value.setter
    def value(self, val):
        """Set and validate field value"""
        if val is not None:
            val = self.validate(val)
        self._value = val

    @abstractmethod
    def validate(self, value: Any) -> Any:
        """Validate and coerce value

        Args:
            value: Value to validate

        Returns:
            Validated/coerced value

        Raises:
            ValueError: If validation fails
        """
        pass

    @abstractmethod
    def serialize(self) -> Any:
        """Serialize value to JSON-compatible format"""
        pass

    @abstractmethod
    def deserialize(self, data: Any):
        """Deserialize value from JSON format"""
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(value={self.value})"
```

---

### `sim2l/schema/types.py` - Concrete Field Types

```python
"""Concrete field type implementations"""

from typing import Any, Optional, List as ListType, Union
import numpy as np
from pint import UnitRegistry

from .field import Field

# Unit registry (shared)
ureg = UnitRegistry()

class Integer(Field):
    """Integer field with min/max validation"""

    def __init__(
        self,
        *,
        min: Optional[int] = None,
        max: Optional[int] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.min = min
        self.max = max

    def validate(self, value: Any) -> int:
        """Validate integer"""
        try:
            val = int(value)
        except (ValueError, TypeError):
            raise ValueError(f"Cannot convert {value} to integer")

        if self.min is not None and val < self.min:
            raise ValueError(f"Value {val} < minimum {self.min}")
        if self.max is not None and val > self.max:
            raise ValueError(f"Value {val} > maximum {self.max}")

        return val

    def serialize(self) -> int:
        return self.value

    def deserialize(self, data: int):
        self.value = data


class Number(Field):
    """Numeric field with units support"""

    def __init__(
        self,
        *,
        units: Optional[str] = None,
        min: Optional[float] = None,
        max: Optional[float] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.units = units
        self.min = min
        self.max = max

    def validate(self, value: Any) -> Union[float, 'Quantity']:
        """Validate number with optional units"""
        # If value already has units (Pint Quantity)
        if hasattr(value, 'magnitude'):
            if self.units:
                # Convert to target units
                value = value.to(self.units)
            magnitude = value.magnitude
        else:
            # Plain number
            try:
                magnitude = float(value)
            except (ValueError, TypeError):
                raise ValueError(f"Cannot convert {value} to number")

            # Attach units if specified
            if self.units:
                value = magnitude * ureg(self.units)

        # Validate range
        if self.min is not None and magnitude < self.min:
            raise ValueError(f"Value {magnitude} < minimum {self.min}")
        if self.max is not None and magnitude > self.max:
            raise ValueError(f"Value {magnitude} > maximum {self.max}")

        return value

    def serialize(self) -> dict:
        """Serialize with units"""
        val = self.value
        if hasattr(val, 'magnitude'):
            return {
                'magnitude': float(val.magnitude),
                'units': str(val.units)
            }
        return {'magnitude': float(val), 'units': None}

    def deserialize(self, data: Union[dict, float]):
        """Deserialize number with units"""
        if isinstance(data, dict):
            magnitude = data['magnitude']
            units = data.get('units')
            if units:
                self.value = magnitude * ureg(units)
            else:
                self.value = magnitude
        else:
            self.value = data


class Text(Field):
    """Text field with optional choices and max length"""

    def __init__(
        self,
        *,
        choices: Optional[ListType[str]] = None,
        maxlen: Optional[int] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.choices = choices
        self.maxlen = maxlen

    def validate(self, value: Any) -> str:
        """Validate text"""
        val = str(value)

        if self.maxlen and len(val) > self.maxlen:
            raise ValueError(f"Text length {len(val)} > maximum {self.maxlen}")

        if self.choices and val not in self.choices:
            raise ValueError(f"Value '{val}' not in allowed choices: {self.choices}")

        return val

    def serialize(self) -> str:
        return self.value

    def deserialize(self, data: str):
        self.value = data


class Array(Field):
    """NumPy array field"""

    def __init__(
        self,
        *,
        dtype: str = 'float',
        shape: Optional[tuple] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.dtype = dtype
        self.shape = shape

    def validate(self, value: Any) -> np.ndarray:
        """Validate array"""
        arr = np.asarray(value, dtype=self.dtype)

        if self.shape:
            # Check shape (None means any size for that dimension)
            if len(arr.shape) != len(self.shape):
                raise ValueError(f"Array rank {len(arr.shape)} != expected {len(self.shape)}")

            for i, (actual, expected) in enumerate(zip(arr.shape, self.shape)):
                if expected is not None and actual != expected:
                    raise ValueError(f"Array dimension {i}: {actual} != expected {expected}")

        return arr

    def serialize(self) -> dict:
        """Serialize array"""
        arr = self.value
        return {
            'data': arr.tolist(),
            'dtype': str(arr.dtype),
            'shape': arr.shape
        }

    def deserialize(self, data: Union[dict, list]):
        """Deserialize array"""
        if isinstance(data, dict):
            arr = np.array(data['data'], dtype=data['dtype'])
            self.value = arr.reshape(data['shape'])
        else:
            self.value = np.array(data, dtype=self.dtype)


class Boolean(Field):
    """Boolean field"""

    def validate(self, value: Any) -> bool:
        """Validate boolean"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ('true', 'yes', '1'):
                return True
            if value.lower() in ('false', 'no', '0'):
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        raise ValueError(f"Cannot convert {value} to boolean")

    def serialize(self) -> bool:
        return self.value

    def deserialize(self, data: bool):
        self.value = data
```

---

### `sim2l/schema/schema.py` - Schema Container

```python
"""Schema container class"""

from typing import Dict, Any
import yaml

from .field import Field
from .types import Integer, Number, Text, Array, Boolean
from .registry import get_field_class

class Schema:
    """Container for input/output schema definition"""

    def __init__(self, fields: Dict[str, Field]):
        """Initialize schema

        Args:
            fields: Dictionary of field name -> Field instance
        """
        self.fields = fields

    def __getattr__(self, name: str) -> Field:
        """Access fields as attributes"""
        if name in self.fields:
            return self.fields[name]
        raise AttributeError(f"Schema has no field '{name}'")

    def __setattr__(self, name: str, value: Any):
        """Set field values"""
        if name == 'fields':
            super().__setattr__(name, value)
        elif name in self.fields:
            self.fields[name].value = value
        else:
            raise AttributeError(f"Schema has no field '{name}'")

    def items(self):
        """Iterate over fields"""
        return self.fields.items()

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data against schema

        Args:
            data: Dictionary of field values

        Returns:
            Validated data

        Raises:
            ValueError: If validation fails
        """
        validated = {}

        # Check required fields
        for name, field in self.fields.items():
            if name in data:
                validated[name] = field.validate(data[name])
            elif field.default is not None:
                validated[name] = field.default
            elif not field.optional:
                raise ValueError(f"Required field '{name}' is missing")

        # Check for unexpected fields
        extra = set(data.keys()) - set(self.fields.keys())
        if extra:
            raise ValueError(f"Unexpected fields: {extra}")

        return validated

    def serialize(self) -> Dict[str, Any]:
        """Serialize all field values"""
        return {
            name: field.serialize()
            for name, field in self.fields.items()
            if field.value is not None
        }

    def deserialize(self, data: Dict[str, Any]):
        """Deserialize field values from data"""
        for name, value in data.items():
            if name in self.fields:
                self.fields[name].deserialize(value)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'Schema':
        """Parse schema from YAML string

        Args:
            yaml_str: YAML schema definition

        Returns:
            Schema instance
        """
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Schema':
        """Parse schema from dictionary

        Args:
            data: Dictionary schema definition

        Returns:
            Schema instance
        """
        fields = {}

        for name, spec in data.items():
            # Get field type
            field_type = spec.get('type', 'Text')
            field_class = get_field_class(field_type)

            # Extract field parameters
            kwargs = {k: v for k, v in spec.items() if k != 'type'}

            # Create field instance
            fields[name] = field_class(**kwargs)

        return cls(fields)

    def __repr__(self):
        return f"Schema({list(self.fields.keys())})"
```

---

### `sim2l/definition/simulation.py` - Simulation Definition

```python
"""Simulation definition class"""

from typing import Optional, Callable, Union
from pathlib import Path
import hashlib

from ..schema import Schema

class SimulationDefinition:
    """Defines a simulation with inputs, outputs, and workflow"""

    def __init__(
        self,
        name: str,
        version: str,
        inputs: Schema,
        outputs: Schema,
        workflow: Union[Callable, Path, bytes],
        *,
        description: str = "",
        author: str = "",
        tags: list = None,
        dependencies: list = None,
    ):
        """Initialize simulation definition

        Args:
            name: Simulation name (unique identifier)
            version: Semantic version (e.g., "1.2.0")
            inputs: Input schema
            outputs: Output schema
            workflow: Workflow implementation (function, notebook path, or bytes)
            description: Human-readable description
            author: Author name
            tags: List of tags for categorization
            dependencies: List of required packages
        """
        self.name = name
        self.version = version
        self.inputs = inputs
        self.outputs = outputs
        self.workflow = workflow
        self.description = description
        self.author = author
        self.tags = tags or []
        self.dependencies = dependencies or []

        # Compute workflow hash for versioning
        self.workflow_hash = self._compute_workflow_hash()

    def _compute_workflow_hash(self) -> str:
        """Compute hash of workflow for change detection"""
        if callable(self.workflow):
            # Hash function source code
            import inspect
            source = inspect.getsource(self.workflow)
            return hashlib.sha256(source.encode()).hexdigest()[:16]
        elif isinstance(self.workflow, bytes):
            # Hash notebook bytes
            return hashlib.sha256(self.workflow).hexdigest()[:16]
        elif isinstance(self.workflow, Path):
            # Hash file contents
            with open(self.workflow, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        return ""

    @classmethod
    def from_notebook(
        cls,
        notebook_path: Union[str, Path],
        name: str,
        version: str,
        **kwargs
    ) -> 'SimulationDefinition':
        """Create simulation definition from Jupyter notebook

        Args:
            notebook_path: Path to notebook file
            name: Simulation name
            version: Version string
            **kwargs: Additional metadata

        Returns:
            SimulationDefinition instance
        """
        from ..definition.parser import parse_notebook

        notebook_path = Path(notebook_path)

        # Parse notebook to extract schemas and code
        inputs, outputs, workflow_bytes = parse_notebook(notebook_path)

        return cls(
            name=name,
            version=version,
            inputs=inputs,
            outputs=outputs,
            workflow=workflow_bytes,
            **kwargs
        )

    def __repr__(self):
        return f"SimulationDefinition(name={self.name}, version={self.version})"
```

---

### `sim2l/repository/repository.py` - Repository Interface

```python
"""Simulation repository for persistence"""

from typing import Optional, List
from pathlib import Path

from .backend import StorageBackend
from .sqlite import SQLiteBackend
from ..definition import SimulationDefinition

class SimulationRepository:
    """Repository for storing and retrieving simulations"""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        backend: Optional[StorageBackend] = None
    ):
        """Initialize repository

        Args:
            db_path: Path to database (for SQLite backend)
            backend: Custom storage backend
        """
        if backend is None:
            from ..config import get_config
            db_path = db_path or get_config().db_path
            backend = SQLiteBackend(db_path)

        self.backend = backend

    def deploy(self, simulation: SimulationDefinition) -> int:
        """Deploy a simulation to the repository

        Args:
            simulation: Simulation definition to deploy

        Returns:
            Simulation ID in database
        """
        return self.backend.deploy(simulation)

    def load(
        self,
        name: str,
        version: Optional[str] = None
    ) -> SimulationDefinition:
        """Load a simulation by name and version

        Args:
            name: Simulation name
            version: Version string (if None, loads latest)

        Returns:
            SimulationDefinition
        """
        return self.backend.load(name, version)

    def list(
        self,
        tags: Optional[List[str]] = None,
        status: str = "active"
    ) -> List[dict]:
        """List available simulations

        Args:
            tags: Filter by tags
            status: Filter by status ("active", "deprecated", "archived")

        Returns:
            List of simulation metadata dictionaries
        """
        return self.backend.list(tags=tags, status=status)

    def exists(self, name: str, version: str) -> bool:
        """Check if simulation exists

        Args:
            name: Simulation name
            version: Version string

        Returns:
            True if exists
        """
        return self.backend.exists(name, version)

    def delete(self, name: str, version: str):
        """Delete a simulation

        Args:
            name: Simulation name
            version: Version to delete
        """
        self.backend.delete(name, version)

    def deprecate(self, name: str, version: str):
        """Mark simulation as deprecated

        Args:
            name: Simulation name
            version: Version to deprecate
        """
        self.backend.update_status(name, version, "deprecated")

    @classmethod
    def create(cls, db_path: Path, backend: str = "sqlite") -> 'SimulationRepository':
        """Create new repository with initialized database

        Args:
            db_path: Path to database
            backend: Backend type ("sqlite", etc.)

        Returns:
            Initialized repository
        """
        if backend == "sqlite":
            SQLiteBackend.create_database(db_path)
            return cls(db_path=db_path)
        else:
            raise ValueError(f"Unknown backend: {backend}")


# Convenience functions
def load_simulation(name: str, version: Optional[str] = None) -> SimulationDefinition:
    """Load simulation from default repository"""
    repo = SimulationRepository()
    return repo.load(name, version)

def list_simulations(**kwargs) -> List[dict]:
    """List simulations from default repository"""
    repo = SimulationRepository()
    return repo.list(**kwargs)
```

---

This provides a solid foundation for the sim2l implementation. The architecture separates concerns cleanly, provides extensibility through abstract base classes, and maintains backward compatibility with simtool through migration tools.

Key improvements over simtool:
1. **Database-first design**: All state in SQLite, not notebooks
2. **Versioning**: Simulations are versioned artifacts
3. **Type-safe schemas**: Better validation and error handling
4. **Pluggable executors**: Easy to add new execution backends
5. **Clean API**: Simpler, more intuitive interface
6. **Testability**: Modular design enables comprehensive testing
