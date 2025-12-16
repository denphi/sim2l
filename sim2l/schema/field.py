"""Base Field class for type system"""

from typing import Any, Optional
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
        self._name = None  # Will be set by Schema

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

    @property
    def type_name(self) -> str:
        """Get type name for serialization"""
        return self.__class__.__name__

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
        """Serialize value to JSON-compatible format

        Returns:
            JSON-serializable representation of value
        """
        pass

    @abstractmethod
    def deserialize(self, data: Any):
        """Deserialize value from JSON format

        Args:
            data: JSON data to deserialize
        """
        pass

    def to_dict(self) -> dict:
        """Convert field definition to dictionary

        Returns:
            Dictionary representation of field metadata
        """
        result = {
            "type": self.type_name,
            "optional": self.optional,
            "description": self.description,
        }

        if self.default is not None:
            result["default"] = self.default

        if self.required_if:
            result["required_if"] = self.required_if

        # Add metadata
        result.update(self.metadata)

        return result

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> 'Field':
        """Create field from dictionary

        Args:
            data: Dictionary with field parameters

        Returns:
            Field instance
        """
        pass

    def __repr__(self):
        name_str = f"{self._name}=" if self._name else ""
        return f"{self.__class__.__name__}({name_str}{self.value})"
