# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Abstract storage backend interface"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from ..definition import SimulationDefinition


class StorageBackend(ABC):
    """Abstract base class for storage backends"""

    @abstractmethod
    def deploy(self, simulation: SimulationDefinition) -> int:
        """Deploy a simulation to storage

        Args:
            simulation: Simulation definition

        Returns:
            Simulation ID
        """
        pass

    @abstractmethod
    def load(self, name: str, version: Optional[str] = None) -> SimulationDefinition:
        """Load a simulation by name and version

        Args:
            name: Simulation name
            version: Version string (if None, loads latest)

        Returns:
            SimulationDefinition
        """
        pass

    @abstractmethod
    def exists(self, name: str, version: str) -> bool:
        """Check if simulation exists

        Args:
            name: Simulation name
            version: Version string

        Returns:
            True if exists
        """
        pass

    @abstractmethod
    def list(
        self,
        tags: Optional[List[str]] = None,
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """List available simulations

        Args:
            tags: Filter by tags
            status: Filter by status

        Returns:
            List of simulation metadata dictionaries
        """
        pass

    @abstractmethod
    def delete(self, name: str, version: str):
        """Delete a simulation

        Args:
            name: Simulation name
            version: Version to delete
        """
        pass

    @abstractmethod
    def update_status(self, name: str, version: str, status: str):
        """Update simulation status

        Args:
            name: Simulation name
            version: Version
            status: New status
        """
        pass

    @abstractmethod
    def get_simulation_id(self, name: str, version: str) -> Optional[int]:
        """Get simulation ID from name and version

        Args:
            name: Simulation name
            version: Version string

        Returns:
            Simulation ID or None if not found
        """
        pass
