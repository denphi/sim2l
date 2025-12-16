"""Shared utility functions"""

from .hash import compute_hash, compute_cache_key
from .serialization import JsonEncoder, JsonDecoder, serialize_value, deserialize_value
from .units import get_unit_registry
from .squid import (
    compute_squid_id,
    parse_squid_id,
    validate_squid_id,
    get_squid_id_for_parameters,
)

__all__ = [
    "compute_hash",
    "compute_cache_key",
    "JsonEncoder",
    "JsonDecoder",
    "serialize_value",
    "deserialize_value",
    "get_unit_registry",
    "compute_squid_id",
    "parse_squid_id",
    "validate_squid_id",
    "get_squid_id_for_parameters",
]
