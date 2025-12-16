"""Hashing utilities for cache keys and content identification"""

import hashlib
import json
from typing import Any, Dict
import numpy as np


def _serialize_value(value):
    """Convert value to JSON-serializable format

    Handles:
    - Pint Quantity objects -> magnitude
    - NumPy types -> Python types
    - Lists/arrays -> lists
    """
    # Handle Pint Quantity
    if hasattr(value, 'magnitude'):
        return _serialize_value(value.magnitude)

    # Handle NumPy types
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()

    # Handle lists/tuples
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]

    # Handle dicts
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}

    return value


def compute_hash(data: Any) -> str:
    """Compute SHA256 hash of data

    Args:
        data: Data to hash (will be JSON serialized)

    Returns:
        Hex digest of hash
    """
    if isinstance(data, (str, bytes)):
        content = data if isinstance(data, bytes) else data.encode()
    else:
        # JSON serialize for consistent hashing
        content = json.dumps(data, sort_keys=True).encode()

    return hashlib.sha256(content).hexdigest()


def compute_cache_key(simulation_id: int, inputs: Dict[str, Any]) -> str:
    """Compute cache key from simulation ID and inputs

    Args:
        simulation_id: Simulation database ID
        inputs: Input parameters dictionary

    Returns:
        Cache key (SHA256 hash)
    """
    # Serialize inputs (handles Pint Quantity, NumPy types, etc.)
    serialized_inputs = {k: _serialize_value(v) for k, v in inputs.items()}

    # Create canonical representation
    cache_data = {
        "simulation_id": simulation_id,
        "inputs": serialized_inputs,
    }

    # Sort keys for consistent hashing
    content = json.dumps(cache_data, sort_keys=True).encode()
    return hashlib.sha256(content).hexdigest()[:16]  # Use first 16 chars
