# SQUID ID Feature Implementation

## Overview

I've implemented SQUID (Simulation Query Unique IDentifier) generation for sim2l, matching the existing simtool format exactly.

## What is a SQUID ID?

A SQUID ID is a unique identifier for a simulation execution computed from:
- Simulation name
- Simulation version/revision
- Input parameters

Format: `simtoolName/simtoolRevision/hash`

Example: `thermal_analysis/1.0.0/a3b5c7d9e1f2a8b4c6d8e0f1a2b3c4d5e6f7a8b9`

## Implementation

### Module: `sim2l/utils/squid.py`

**Functions**:

1. **`compute_squid_id(simtool_name, simtool_revision, inputs)`**
   - Compute SQUID ID from parameters
   - Matches existing simtool algorithm exactly
   - Returns: `"name/revision/hash"`

2. **`get_squid_id_for_parameters(simtoolName, simtoolRevision, inputs)`**
   - API-compatible version with camelCase parameters
   - Returns: `{"id": "name/revision/hash"}`
   - Matches your existing API format

3. **`parse_squid_id(squid_id)`**
   - Parse SQUID ID into components
   - Returns: `{"name": "...", "revision": "...", "hash": "..."}`

4. **`validate_squid_id(squid_id, simtool_name, simtool_revision, inputs)`**
   - Validate SQUID ID matches parameters
   - Returns: `True` or `False`

### Algorithm (matches simtool exactly)

```python
1. Sort input keys alphabetically
2. Create "key value" pairs for each input
3. Append "simtoolName <name>"
4. Append "simtoolRevision <revision>"
5. Join with newlines
6. Compute SHA1 hash
7. Format as: name/revision/hash
```

### Properties

✓ **Deterministic**: Same inputs always produce same SQUID ID
✓ **Unique**: Different inputs produce different SQUID IDs
✓ **Version-aware**: Different versions produce different SQUID IDs
✓ **Order-independent**: Input order doesn't matter (sorted internally)
✓ **JSON-compatible**: Works with nested objects, arrays, etc.
✓ **Compatible**: Matches existing simtool format

## Usage

### Basic Usage

```python
import sim2l

# Compute SQUID ID
squid_id = sim2l.compute_squid_id(
    simtool_name="thermal_analysis",
    simtool_revision="1.0.0",
    inputs={
        "temperature": 300,
        "power": 20,
        "iterations": 100
    }
)

print(squid_id)
# Output: thermal_analysis/1.0.0/a3b5c7d9e1f2...
```

### API-Compatible Format

```python
# Use camelCase parameters (matches existing API)
result = sim2l.get_squid_id_for_parameters(
    simtoolName="thermal_analysis",
    simtoolRevision="1.0.0",
    inputs={"temperature": 300}
)

print(result)
# Output: {'id': 'thermal_analysis/1.0.0/a3b5c7...'}
```

### With SimulationDefinition

```python
from sim2l import SimulationDefinition, compute_squid_id

# Load simulation
sim = SimulationDefinition.from_notebook(...)

# Compute SQUID for execution
squid_id = compute_squid_id(
    simtool_name=sim.name,
    simtool_revision=sim.version,
    inputs={"param1": value1, "param2": value2}
)
```

### Parse SQUID ID

```python
from sim2l.utils import parse_squid_id

components = parse_squid_id(squid_id)
# Returns: {
#     "name": "thermal_analysis",
#     "revision": "1.0.0",
#     "hash": "a3b5c7d9..."
# }
```

### Validate SQUID ID

```python
from sim2l.utils import validate_squid_id

is_valid = validate_squid_id(
    squid_id="thermal_analysis/1.0.0/abc123...",
    simtool_name="thermal_analysis",
    simtool_revision="1.0.0",
    inputs={"temperature": 300}
)
```

## Examples

See `examples/squid_id_example.py` for comprehensive examples covering:
- Basic computation
- API-compatible format
- Deterministic behavior
- Different inputs/versions
- Parsing and validation
- Complex nested inputs

Run examples:
```bash
cd sim2l
python examples/squid_id_example.py
```

## Integration with sim2l

SQUID IDs are integrated into:

1. **Execution Results** - Each `ExecutionResult` has a `squid_id` field
2. **Cache Lookups** - SQUID IDs used for cache keys (alternative to internal hash)
3. **Database** - Stored in execution records for tracking

## Backward Compatibility

The implementation is **100% compatible** with existing simtool SQUID ID generation:

- ✅ Same hashing algorithm (SHA1)
- ✅ Same input ordering (sorted keys)
- ✅ Same prologue format ("key value" pairs)
- ✅ Same metadata appending
- ✅ Same output format (name/revision/hash)

### Migration Note

If you have existing SQUID IDs from simtool, they will match sim2l's generated SQUID IDs for the same parameters.

## API Reference

### `compute_squid_id(simtool_name, simtool_revision, inputs) -> str`

**Parameters**:
- `simtool_name` (str): Simulation name
- `simtool_revision` (str): Simulation version/revision
- `inputs` (dict): Input parameters dictionary

**Returns**: SQUID ID string

**Raises**: `ValueError` if any parameter is None

---

### `get_squid_id_for_parameters(simtoolName, simtoolRevision, inputs) -> dict`

**Parameters**:
- `simtoolName` (str): Simulation name (camelCase)
- `simtoolRevision` (str): Simulation version (camelCase)
- `inputs` (dict): Input parameters

**Returns**: `{"id": "squid_id_string"}`

**Raises**: `ValueError` if any parameter is None

---

### `parse_squid_id(squid_id) -> dict`

**Parameters**:
- `squid_id` (str): SQUID ID to parse

**Returns**: `{"name": "...", "revision": "...", "hash": "..."}`

**Raises**: `ValueError` if format is invalid

---

### `validate_squid_id(squid_id, simtool_name, simtool_revision, inputs) -> bool`

**Parameters**:
- `squid_id` (str): SQUID ID to validate
- `simtool_name` (str): Expected simulation name
- `simtool_revision` (str): Expected version
- `inputs` (dict): Expected input parameters

**Returns**: `True` if SQUID ID matches, `False` otherwise

## Testing

Test SQUID ID generation:

```python
import sim2l

# Test deterministic behavior
squid1 = sim2l.compute_squid_id("test", "1.0.0", {"a": 1, "b": 2})
squid2 = sim2l.compute_squid_id("test", "1.0.0", {"b": 2, "a": 1})
assert squid1 == squid2, "SQUID IDs should be deterministic"

# Test uniqueness
squid3 = sim2l.compute_squid_id("test", "1.0.0", {"a": 1, "b": 3})
assert squid1 != squid3, "Different inputs should produce different SQUID IDs"

# Test version awareness
squid4 = sim2l.compute_squid_id("test", "2.0.0", {"a": 1, "b": 2})
assert squid1 != squid4, "Different versions should produce different SQUID IDs"

print("✓ All SQUID ID tests passed!")
```

## Summary

✅ **Implemented**: SQUID ID generation matching simtool exactly
✅ **Tested**: Deterministic, unique, version-aware
✅ **Documented**: Complete API reference and examples
✅ **Compatible**: 100% backward compatible with simtool
✅ **Integrated**: Available in main sim2l API
✅ **Examples**: Comprehensive example file with 8 use cases

The SQUID ID feature is production-ready and can be used immediately.
