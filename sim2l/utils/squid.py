"""SQUID ID generation for simulation executions

SQUID (Simulation Query Unique IDentifier) provides a consistent way to
generate unique IDs for simulation executions based on:
- Simulation name
- Simulation version/revision
- Input parameters

This enables:
- Cache lookups
- Result deduplication
- Execution tracking
"""

import hashlib
import codecs
import json
from typing import Dict, Any
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


def compute_squid_id(
    simtool_name: str,
    simtool_revision: str,
    inputs: Dict[str, Any]
) -> str:
    """Compute SQUID ID for a simulation execution

    The SQUID ID is computed as:
    1. Create prologue with sorted inputs in format "key value"
    2. Append simtoolName and simtoolRevision
    3. SHA1 hash the prologue
    4. Format as: simtoolName/simtoolRevision/hash

    This matches the existing simtool SQUID generation for compatibility.

    Args:
        simtool_name: Simulation name
        simtool_revision: Simulation version/revision
        inputs: Dictionary of input parameters

    Returns:
        SQUID ID string in format: "name/revision/hash"

    Example:
        >>> compute_squid_id(
        ...     simtool_name="thermal_analysis",
        ...     simtool_revision="1.0.0",
        ...     inputs={"temperature": 300, "power": 20}
        ... )
        'thermal_analysis/1.0.0/a3b5c7d9e1f2...'
    """
    # Validate inputs
    if simtool_name is None:
        raise ValueError("simtool_name parameter is required")
    if simtool_revision is None:
        raise ValueError("simtool_revision parameter is required")
    if inputs is None:
        raise ValueError("inputs parameter is required")

    # Serialize inputs (handles Pint Quantity, NumPy types, etc.)
    serialized_inputs = {k: _serialize_value(v) for k, v in inputs.items()}

    # Ensure inputs are JSON-serializable and sorted
    inputs = json.loads(json.dumps(serialized_inputs, sort_keys=True))

    # Create sorted list of input keys
    kinputs = sorted(list(inputs.keys()))

    # Create "key value" pairs
    linputs = [str(k) + " " + str(inputs[k]) for k in kinputs]

    # Append metadata
    linputs.append("simtoolName " + str(simtool_name))
    linputs.append("simtoolRevision " + str(simtool_revision))

    # Create prologue
    prologue = '\n'.join(linputs)

    # Compute SHA1 hash
    hasher = hashlib.sha1()
    hasher.update(memoryview(codecs.encode(prologue, 'utf-8')))

    # Format SQUID ID
    squid_id = str(simtool_name) + "/" + str(simtool_revision) + "/" + hasher.hexdigest()

    return squid_id


def parse_squid_id(squid_id: str) -> Dict[str, str]:
    """Parse SQUID ID into components

    Args:
        squid_id: SQUID ID string

    Returns:
        Dictionary with keys: name, revision, hash

    Example:
        >>> parse_squid_id("thermal_analysis/1.0.0/a3b5c7...")
        {'name': 'thermal_analysis', 'revision': '1.0.0', 'hash': 'a3b5c7...'}
    """
    parts = squid_id.split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid SQUID ID format: {squid_id}")

    return {
        "name": parts[0],
        "revision": parts[1],
        "hash": parts[2],
    }


def validate_squid_id(
    squid_id: str,
    simtool_name: str,
    simtool_revision: str,
    inputs: Dict[str, Any]
) -> bool:
    """Validate that SQUID ID matches the given parameters

    Args:
        squid_id: SQUID ID to validate
        simtool_name: Simulation name
        simtool_revision: Simulation version
        inputs: Input parameters

    Returns:
        True if SQUID ID matches parameters
    """
    expected_squid = compute_squid_id(simtool_name, simtool_revision, inputs)
    return squid_id == expected_squid


# Alias for compatibility
def get_squid_id_for_parameters(
    simtoolName: str,
    simtoolRevision: str,
    inputs: Dict[str, Any]
) -> Dict[str, str]:
    """Get SQUID ID for parameters (API-compatible format)

    This function matches the existing API format with camelCase parameters.

    Args:
        simtoolName: Simulation name
        simtoolRevision: Simulation version
        inputs: Input parameters dictionary

    Returns:
        Dictionary with 'id' key containing SQUID ID

    Example:
        >>> get_squid_id_for_parameters(
        ...     simtoolName="thermal_analysis",
        ...     simtoolRevision="1.0.0",
        ...     inputs={"temperature": 300}
        ... )
        {'id': 'thermal_analysis/1.0.0/abc123...'}
    """
    squid_id = compute_squid_id(simtoolName, simtoolRevision, inputs)
    return {"id": squid_id}
