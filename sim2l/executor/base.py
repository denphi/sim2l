"""Base Executor class"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path

from ..definition import SimulationDefinition
from ..result import ExecutionResult


class Executor(ABC):
    """Abstract base class for simulation executors"""

    def __init__(
        self,
        cache: bool = True,
        output_dir: Optional[Path] = None,
    ):
        """Initialize executor

        Args:
            cache: Enable caching
            output_dir: Output directory for execution artifacts
        """
        self.cache = cache
        self.output_dir = output_dir

    @abstractmethod
    def execute(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
        run_name: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a simulation

        Args:
            simulation: Simulation definition to execute
            inputs: Input parameters
            run_name: Optional run name (UUID generated if None)

        Returns:
            ExecutionResult with outputs

        Raises:
            ExecutionError: If execution fails
        """
        pass

    @abstractmethod
    def check_cache(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
    ) -> Optional[ExecutionResult]:
        """Check if cached result exists

        Args:
            simulation: Simulation definition
            inputs: Input parameters

        Returns:
            Cached ExecutionResult or None
        """
        pass

    def prepare_inputs(
        self,
        simulation: SimulationDefinition,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare and validate inputs

        Args:
            simulation: Simulation definition
            inputs: Raw input parameters

        Returns:
            Validated input parameters

        Raises:
            ValueError: If validation fails
        """
        # Validate inputs against schema
        validated = simulation.inputs.validate(inputs)

        # Extract values from Field objects
        input_values = {}
        for name, value in validated.items():
            # If value is a Field instance, get its actual value
            if hasattr(value, 'value'):
                input_values[name] = value.value
            else:
                input_values[name] = value

        return input_values

    def __repr__(self):
        return f"{self.__class__.__name__}(cache={self.cache})"
