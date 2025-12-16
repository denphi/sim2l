"""Simulation repository for persistence"""

from typing import Optional, List, Dict, Any
from pathlib import Path

from .backend import StorageBackend
from .sqlite import SQLiteBackend
from ..definition import SimulationDefinition
from ..config import get_config


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
    ) -> List[Dict[str, Any]]:
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

    def get_simulation_id(self, name: str, version: str) -> Optional[int]:
        """Get simulation database ID

        Args:
            name: Simulation name
            version: Version string

        Returns:
            Simulation ID or None
        """
        return self.backend.get_simulation_id(name, version)

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
    """Load simulation from default repository

    Args:
        name: Simulation name
        version: Version (if None, loads latest)

    Returns:
        SimulationDefinition
    """
    repo = SimulationRepository()
    return repo.load(name, version)


def list_simulations(**kwargs) -> List[Dict[str, Any]]:
    """List simulations from default repository

    Args:
        **kwargs: Filter arguments (tags, status)

    Returns:
        List of simulation metadata
    """
    repo = SimulationRepository()
    return repo.list(**kwargs)
