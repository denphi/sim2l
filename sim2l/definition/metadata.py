"""Simulation metadata handling"""

from typing import List, Optional
from datetime import datetime


class SimulationMetadata:
    """Metadata for a simulation"""

    def __init__(
        self,
        name: str,
        version: str,
        description: str = "",
        author: str = "",
        tags: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        created_at: Optional[datetime] = None,
    ):
        """Initialize metadata

        Args:
            name: Simulation name
            version: Semantic version
            description: Description
            author: Author name
            tags: List of tags
            dependencies: List of package dependencies
            created_at: Creation timestamp
        """
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.tags = tags or []
        self.dependencies = dependencies or []
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SimulationMetadata':
        """Create from dictionary"""
        created_at = data.get('created_at')
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            name=data['name'],
            version=data['version'],
            description=data.get('description', ''),
            author=data.get('author', ''),
            tags=data.get('tags', []),
            dependencies=data.get('dependencies', []),
            created_at=created_at,
        )
