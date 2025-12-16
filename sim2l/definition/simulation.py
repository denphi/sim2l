"""Simulation definition class"""

from typing import Optional, Callable, Union, List
from pathlib import Path
import hashlib
import pickle

from ..schema import InputSchema, OutputSchema
from .metadata import SimulationMetadata


class SimulationDefinition:
    """Defines a simulation with inputs, outputs, and workflow"""

    def __init__(
        self,
        name: str,
        version: str,
        inputs: InputSchema,
        outputs: OutputSchema,
        workflow: Union[Callable, Path, bytes],
        *,
        description: str = "",
        author: str = "",
        tags: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        workflow_type: str = "notebook",
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
            workflow_type: Type of workflow ("notebook", "function", "dag")
        """
        self.metadata = SimulationMetadata(
            name=name,
            version=version,
            description=description,
            author=author,
            tags=tags,
            dependencies=dependencies,
        )

        self.inputs = inputs
        self.outputs = outputs
        self.workflow = workflow
        self.workflow_type = workflow_type

        # Compute workflow hash for versioning
        self.workflow_hash = self._compute_workflow_hash()

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def author(self) -> str:
        return self.metadata.author

    @property
    def tags(self) -> List[str]:
        return self.metadata.tags

    @property
    def dependencies(self) -> List[str]:
        return self.metadata.dependencies

    def _compute_workflow_hash(self) -> str:
        """Compute hash of workflow for change detection"""
        if callable(self.workflow):
            # Hash function source code
            import inspect
            try:
                source = inspect.getsource(self.workflow)
                return hashlib.sha256(source.encode()).hexdigest()[:16]
            except Exception:
                # If source not available, use pickled function
                pickled = pickle.dumps(self.workflow)
                return hashlib.sha256(pickled).hexdigest()[:16]

        elif isinstance(self.workflow, bytes):
            # Hash notebook bytes
            return hashlib.sha256(self.workflow).hexdigest()[:16]

        elif isinstance(self.workflow, Path):
            # Hash file contents
            with open(self.workflow, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]

        return ""

    def get_workflow_bytes(self) -> bytes:
        """Get workflow as bytes for storage

        Returns:
            Workflow as bytes
        """
        if isinstance(self.workflow, bytes):
            return self.workflow

        elif isinstance(self.workflow, Path):
            with open(self.workflow, 'rb') as f:
                return f.read()

        elif callable(self.workflow):
            # Pickle the function
            return pickle.dumps(self.workflow)

        else:
            raise ValueError(f"Cannot convert workflow of type {type(self.workflow)} to bytes")

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
        from .parser import parse_notebook

        notebook_path = Path(notebook_path)

        # Parse notebook to extract schemas and code
        inputs, outputs, workflow_bytes = parse_notebook(notebook_path)

        return cls(
            name=name,
            version=version,
            inputs=inputs,
            outputs=outputs,
            workflow=workflow_bytes,
            workflow_type="notebook",
            **kwargs
        )

    @classmethod
    def from_function(
        cls,
        func: Callable,
        name: str,
        version: str,
        inputs: InputSchema,
        outputs: OutputSchema,
        **kwargs
    ) -> 'SimulationDefinition':
        """Create simulation definition from Python function

        Args:
            func: Simulation function
            name: Simulation name
            version: Version string
            inputs: Input schema
            outputs: Output schema
            **kwargs: Additional metadata

        Returns:
            SimulationDefinition instance
        """
        return cls(
            name=name,
            version=version,
            inputs=inputs,
            outputs=outputs,
            workflow=func,
            workflow_type="function",
            **kwargs
        )

    def run(self, executor=None, **inputs):
        """Execute simulation with given inputs

        Args:
            executor: Executor instance or type string ('local', 'notebook')
            **inputs: Input parameters as keyword arguments

        Returns:
            ExecutionResult

        Example:
            >>> sim = load_simulation("my_sim")
            >>> result = sim.run(temperature=350, power=20)
            >>> print(result.outputs.max_temperature)
        """
        # Import here to avoid circular dependency
        from ..executor import LocalExecutor, NotebookExecutor
        from ..config import get_config

        # Determine executor
        if executor is None:
            # Use default from config
            executor_type = get_config().default_executor
        elif isinstance(executor, str):
            executor_type = executor
        else:
            # Already an Executor instance
            return executor.execute(self, inputs)

        # Create executor instance
        if executor_type == "local":
            executor_inst = LocalExecutor()
        elif executor_type == "notebook":
            executor_inst = NotebookExecutor()
        else:
            raise ValueError(f"Unknown executor type: {executor_type}")

        # Execute
        return executor_inst.execute(self, inputs)

    def __repr__(self):
        return f"SimulationDefinition(name={self.name}, version={self.version})"
