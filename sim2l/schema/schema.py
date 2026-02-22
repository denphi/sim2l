# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Schema container class"""

from typing import Dict, Any, Iterator
import yaml

from .field import Field
from .registry import get_field_class


class Schema:
    """Container for input/output schema definition"""

    def __init__(self, fields: Dict[str, Field]):
        """Initialize schema

        Args:
            fields: Dictionary of field name -> Field instance
        """
        self.fields = fields

        # Set field names
        for name, field in self.fields.items():
            field._name = name

    def __getattr__(self, name: str) -> Field:
        """Access fields as attributes"""
        if name in ('fields',):
            return super().__getattribute__(name)

        if name in self.fields:
            return self.fields[name]

        raise AttributeError(f"Schema has no field '{name}'")

    def __setattr__(self, name: str, value: Any):
        """Set field values"""
        if name == 'fields':
            super().__setattr__(name, value)
        elif hasattr(self, 'fields') and name in self.fields:
            self.fields[name].value = value
        else:
            super().__setattr__(name, value)

    def __getitem__(self, name: str) -> Field:
        """Dictionary-style access"""
        return self.fields[name]

    def __contains__(self, name: str) -> bool:
        """Check if field exists"""
        return name in self.fields

    def __iter__(self) -> Iterator[str]:
        """Iterate over field names"""
        return iter(self.fields)

    def items(self):
        """Iterate over fields"""
        return self.fields.items()

    def keys(self):
        """Get field names"""
        return self.fields.keys()

    def values(self):
        """Get field objects"""
        return self.fields.values()

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

    def set_values(self, data: Dict[str, Any]):
        """Set field values from dictionary

        Args:
            data: Dictionary of field values
        """
        validated = self.validate(data)
        for name, value in validated.items():
            self.fields[name].value = value

    def get_values(self) -> Dict[str, Any]:
        """Get current field values

        Returns:
            Dictionary of field values
        """
        return {
            name: field.value
            for name, field in self.fields.items()
            if field.value is not None
        }

    def serialize(self) -> Dict[str, Any]:
        """Serialize all field values

        Returns:
            Dictionary of serialized values
        """
        return {
            name: field.serialize()
            for name, field in self.fields.items()
            if field.value is not None
        }

    def deserialize(self, data: Dict[str, Any]):
        """Deserialize field values from data

        Args:
            data: Dictionary of serialized values
        """
        for name, value in data.items():
            if name in self.fields:
                self.fields[name].deserialize(value)

    def to_dict(self) -> Dict[str, Any]:
        """Convert schema definition to dictionary

        Returns:
            Dictionary representation of schema
        """
        return {
            name: field.to_dict()
            for name, field in self.fields.items()
        }

    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'Schema':
        """Parse schema from YAML string

        Args:
            yaml_str: YAML schema definition

        Returns:
            Schema instance
        """
        data = yaml.safe_load(yaml_str)
        if data is None:
            data = {}
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

            # Create field instance from dictionary
            fields[name] = field_class.from_dict(spec)

        return cls(fields)

    def __repr__(self):
        return f"Schema({list(self.fields.keys())})"


class InputSchema(Schema):
    """Schema for simulation inputs"""
    pass


class OutputSchema(Schema):
    """Schema for simulation outputs"""
    pass
