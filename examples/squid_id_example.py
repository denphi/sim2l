"""Example: Computing SQUID IDs for simulation executions

SQUID (Simulation Query Unique IDentifier) provides a consistent way to
generate unique IDs for simulation executions.
"""

import sim2l

# Example 1: Basic SQUID ID computation
print("=" * 60)
print("Example 1: Basic SQUID ID Computation")
print("=" * 60)

squid_id = sim2l.compute_squid_id(
    simtool_name="thermal_analysis",
    simtool_revision="1.0.0",
    inputs={
        "temperature": 300,
        "power": 20,
        "iterations": 100
    }
)

print(f"SQUID ID: {squid_id}")
print()

# Example 2: API-compatible format (matches existing API)
print("=" * 60)
print("Example 2: API-Compatible Format")
print("=" * 60)

result = sim2l.get_squid_id_for_parameters(
    simtoolName="thermal_analysis",
    simtoolRevision="1.0.0",
    inputs={
        "temperature": 300,
        "power": 20,
        "iterations": 100
    }
)

print(f"Result: {result}")
print(f"SQUID ID: {result['id']}")
print()

# Example 3: Same inputs = same SQUID ID (deterministic)
print("=" * 60)
print("Example 3: Deterministic SQUID IDs")
print("=" * 60)

squid1 = sim2l.compute_squid_id(
    simtool_name="test_sim",
    simtool_revision="1.0.0",
    inputs={"a": 1, "b": 2, "c": 3}
)

squid2 = sim2l.compute_squid_id(
    simtool_name="test_sim",
    simtool_revision="1.0.0",
    inputs={"c": 3, "a": 1, "b": 2}  # Different order
)

print(f"SQUID 1: {squid1}")
print(f"SQUID 2: {squid2}")
print(f"Same? {squid1 == squid2}")
print()

# Example 4: Different inputs = different SQUID ID
print("=" * 60)
print("Example 4: Different Inputs = Different IDs")
print("=" * 60)

squid_300k = sim2l.compute_squid_id(
    simtool_name="thermal_analysis",
    simtool_revision="1.0.0",
    inputs={"temperature": 300}
)

squid_350k = sim2l.compute_squid_id(
    simtool_name="thermal_analysis",
    simtool_revision="1.0.0",
    inputs={"temperature": 350}
)

print(f"300K: {squid_300k}")
print(f"350K: {squid_350k}")
print(f"Same? {squid_300k == squid_350k}")
print()

# Example 5: Different versions = different SQUID ID
print("=" * 60)
print("Example 5: Different Versions = Different IDs")
print("=" * 60)

squid_v1 = sim2l.compute_squid_id(
    simtool_name="test_sim",
    simtool_revision="1.0.0",
    inputs={"param": 100}
)

squid_v2 = sim2l.compute_squid_id(
    simtool_name="test_sim",
    simtool_revision="2.0.0",
    inputs={"param": 100}
)

print(f"v1.0.0: {squid_v1}")
print(f"v2.0.0: {squid_v2}")
print(f"Same? {squid_v1 == squid_v2}")
print()

# Example 6: Parse SQUID ID
print("=" * 60)
print("Example 6: Parse SQUID ID")
print("=" * 60)

from sim2l.utils import parse_squid_id

components = parse_squid_id(squid_id)
print(f"Original: {squid_id}")
print(f"Components:")
print(f"  Name: {components['name']}")
print(f"  Revision: {components['revision']}")
print(f"  Hash: {components['hash']}")
print()

# Example 7: Validate SQUID ID
print("=" * 60)
print("Example 7: Validate SQUID ID")
print("=" * 60)

from sim2l.utils import validate_squid_id

# Correct inputs
is_valid = validate_squid_id(
    squid_id=squid_id,
    simtool_name="thermal_analysis",
    simtool_revision="1.0.0",
    inputs={
        "temperature": 300,
        "power": 20,
        "iterations": 100
    }
)
print(f"Valid with correct inputs? {is_valid}")

# Wrong inputs
is_valid_wrong = validate_squid_id(
    squid_id=squid_id,
    simtool_name="thermal_analysis",
    simtool_revision="1.0.0",
    inputs={"temperature": 350}  # Different
)
print(f"Valid with wrong inputs? {is_valid_wrong}")
print()

# Example 8: Use with complex inputs
print("=" * 60)
print("Example 8: Complex Inputs")
print("=" * 60)

complex_squid = sim2l.compute_squid_id(
    simtool_name="device_simulation",
    simtool_revision="2.1.5",
    inputs={
        "material": "silicon",
        "temperature": 300,
        "voltage": 5.0,
        "mesh_points": [0.0, 0.5, 1.0, 1.5, 2.0],
        "enable_advanced": True,
        "metadata": {
            "user": "john_doe",
            "project": "test_project"
        }
    }
)

print(f"Complex SQUID: {complex_squid}")
print()

print("=" * 60)
print("Summary")
print("=" * 60)
print("SQUID IDs are:")
print("  ✓ Deterministic (same inputs = same ID)")
print("  ✓ Unique (different inputs = different ID)")
print("  ✓ Version-aware (different versions = different ID)")
print("  ✓ JSON-serializable (works with complex nested structures)")
print("  ✓ Compatible with existing simtool format")
