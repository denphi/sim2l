"""Typed output data accessor"""

from typing import Any, Dict
from ..schema import OutputSchema


class OutputData:
    """Typed accessor for simulation outputs

    Provides attribute-style access to outputs with proper typing.
    """

    def __init__(self, schema: OutputSchema, data: Dict[str, Any]):
        """Initialize output data

        Args:
            schema: Output schema defining expected outputs
            data: Dictionary of output values
        """
        self._schema = schema
        self._data = data

    def __getattr__(self, name: str) -> Any:
        """Get output value by name

        Args:
            name: Output name

        Returns:
            Output value with proper typing

        Raises:
            AttributeError: If output not found
        """
        if name.startswith('_'):
            return super().__getattribute__(name)

        if name not in self._schema:
            raise AttributeError(f"Output '{name}' not found in schema")

        if name not in self._data:
            # Return default if available
            field = self._schema[name]
            if field.optional:
                return None
            raise AttributeError(f"Required output '{name}' not found in data")

        # Deserialize using schema
        field = self._schema[name]
        value = self._data[name]

        # If value is already deserialized, return it
        if hasattr(field, '_deserialized_cache') and name in field._deserialized_cache:
            return field._deserialized_cache[name]

        # Deserialize
        field.deserialize(value)
        return field.value

    def __contains__(self, name: str) -> bool:
        """Check if output exists"""
        return name in self._data

    def keys(self):
        """Get output names"""
        return self._data.keys()

    def items(self):
        """Iterate over outputs"""
        for name in self._data.keys():
            yield name, getattr(self, name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary

        Returns:
            Dictionary of output values
        """
        return self._data.copy()

    def __repr__(self):
        return f"OutputData({list(self._data.keys())})"
