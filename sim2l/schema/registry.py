"""Field type registry for dynamic type lookup"""

from typing import Dict, Type
from .field import Field

# Global registry of field types
_FIELD_REGISTRY: Dict[str, Type[Field]] = {}


def register_field_type(name: str, field_class: Type[Field]):
    """Register a field type

    Args:
        name: Type name (e.g., "Integer", "Number")
        field_class: Field class
    """
    _FIELD_REGISTRY[name] = field_class


def get_field_class(name: str) -> Type[Field]:
    """Get field class by name

    Args:
        name: Type name

    Returns:
        Field class

    Raises:
        ValueError: If type not found
    """
    if name not in _FIELD_REGISTRY:
        raise ValueError(f"Unknown field type: {name}")
    return _FIELD_REGISTRY[name]


def _register_builtin_types():
    """Register built-in field types"""
    from .types import (
        Integer,
        Number,
        Text,
        Array,
        Image,
        Element,
        Boolean,
        List,
        Dict,
    )

    register_field_type("Integer", Integer)
    register_field_type("Number", Number)
    register_field_type("Text", Text)
    register_field_type("Array", Array)
    register_field_type("Image", Image)
    register_field_type("Element", Element)
    register_field_type("Boolean", Boolean)
    register_field_type("List", List)
    register_field_type("Dict", Dict)


# Register built-in types on module import
_register_builtin_types()
