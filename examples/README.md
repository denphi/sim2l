# sim2l Examples

This directory contains comprehensive examples demonstrating sim2l's capabilities.

## Examples Overview

### 1. File Processing Example ⭐ NEW
**Complete workflow for file-based simulations**

- **Files:**
  - [file_processing_simulation.ipynb](file_processing_simulation.ipynb) - Notebook that processes CSV files
  - [use_file_processing.py](use_file_processing.py) - Execute simulation with different modes
  - [sample_data.csv](sample_data.csv) - Sample input data
  - [FILE_PROCESSING_EXAMPLE.md](FILE_PROCESSING_EXAMPLE.md) - Complete documentation

- **Features:**
  - File path inputs (Text type with absolute paths)
  - File path outputs (generated files)
  - Multiple processing modes (summarize, transform, analyze)
  - Output format selection (CSV, JSON, TXT)
  - Database storage of file paths
  - SQUID-based caching

- **Run:**
  ```bash
  cd examples
  python3 use_file_processing.py
  ```

---

### 2. Thermal Simulation Example
**2D thermal diffusion with physical units**

- **Files:**
  - [thermal_simulation.ipynb](thermal_simulation.ipynb) - 2D thermal diffusion simulation
  - [use_thermal_simulation.py](use_thermal_simulation.py) - Complete workflow demonstration
  - [NOTEBOOK_SETUP.md](NOTEBOOK_SETUP.md) - How to set up notebooks

- **Features:**
  - Physical units (temperature in kelvin, power in watt)
  - NumPy array outputs (temperature distribution)
  - Image outputs (thermal plots)
  - IPython magic commands (`%%sim2l_inputs`, `%%sim2l_outputs`)
  - Parameter sweeps
  - Caching demonstration

- **Run:**
  ```bash
  cd examples
  python3 use_thermal_simulation.py
  ```

---

### 3. SQUID ID Example
**Understanding SQUID identifiers**

- **File:** [squid_id_example.py](squid_id_example.py)

- **Features:**
  - SQUID ID computation
  - Format: `name/version/hash`
  - Deterministic hashing
  - Cache key generation
  - Result deduplication

- **Run:**
  ```bash
  python3 squid_id_example.py
  ```

---

### 4. Executor Example
**Using different execution backends**

- **File:** [executor_example.py](executor_example.py)

- **Features:**
  - LocalExecutor (Python functions)
  - NotebookExecutor (Papermill)
  - Caching configuration
  - Execution tracking

- **Run:**
  ```bash
  python3 executor_example.py
  ```

---

## Quick Start Guide

### 1. Install sim2l

```bash
cd sim2l
pip install -e .
```

### 2. Create a Notebook Simulation

```python
# Cell 1: Load extension
%load_ext sim2l.notebook

# Cell 2: Define inputs
%%sim2l_inputs
temperature:
  type: Number
  units: kelvin
  default: 300

# Cell 3: Define outputs
%%sim2l_outputs
result:
  type: Number
  units: kelvin

# Cell 4: Get inputs
import sim2l
try:
    _ = temperature  # Check if Papermill injected
except NameError:
    temperature = 300  # Default for interactive

# Cell 5: Simulation
result = temperature * 1.1

# Cell 6: Save outputs
sim2l.save_outputs(result=result)
```

### 3. Deploy and Execute

```python
import sim2l
from sim2l.executor import NotebookExecutor

# Deploy
sim2l.configure(db_path="my_sims.db")
sim2l.deploy_simulation(
    notebook="my_simulation.ipynb",
    name="my_sim",
    version="1.0.0"
)

# Execute
sim = sim2l.load_simulation("my_sim")
executor = NotebookExecutor(cache=True)
result = sim.run(temperature=350, executor=executor)

print(f"Result: {result.outputs.result}")
print(f"SQUID ID: {result.squid_id}")
```

---

## Key Concepts

### SQUID IDs

**Format:** `simulation_name/version/hash`

**Purpose:**
- Unique identifier for each simulation execution
- Based on simulation name + version + input parameters
- Same inputs = same SQUID ID = cached result
- Enables O(1) cache lookups

**Example:**
```
thermal_analysis/1.0.0/af1f029da410a4ff14b55c28196dcfbe386668da
└─ name ──────┘└─ ver ┘└──────────── SHA1 hash ─────────────────┘
```

### Database Storage

**Tables:**
- `simulations` - Deployed simulation definitions
- `executions` - Execution history with metadata
- `outputs` - Simulation outputs (serialized)
- `cache` - SQUID ID → execution_id mapping
- `artifacts` - Large binary artifacts
- `simulation_tags` - Tags for discovery

**Key Feature:** Database is the source of truth, not notebooks!

### File Handling

**Input Files:**
```python
# Use absolute paths
input_file = str(Path("data.csv").resolve())
result = sim.run(input_file=input_file)
```

**Output Files:**
```python
# In notebook - relative paths OK
df.to_csv("output.csv")
sim2l.save_outputs(output_file="output.csv")

# File path stored in database
# File contents remain in temp directory
```

### save_outputs()

**How it works:**
1. Saves to SQLite database (primary storage)
2. Uses environment variables to identify execution
3. Serializes complex types (NumPy arrays, Pint Quantity)
4. Optionally saves to scrapbook (backward compatibility)

**Example:**
```python
sim2l.save_outputs(
    temperature=350.5,              # Number
    distribution=numpy_array,        # NumPy array
    plot="thermal_plot.png",        # File path
    converged=True                   # Boolean
)
```

---

## Common Patterns

### Parameter Sweep

```python
executor = NotebookExecutor(cache=True)
results = []

for temp in [300, 350, 400, 450]:
    result = sim.run(temperature=temp, executor=executor)
    results.append({
        'temp': temp,
        'output': result.outputs.max_temperature
    })

# Cached results load instantly!
```

### Error Handling

```python
result = sim.run(temperature=350, executor=executor)

if result.status == "completed":
    print(f"Success: {result.outputs}")
elif result.status == "failed":
    print(f"Error: {result.error_message}")
```

### Version Management

```python
# Deploy multiple versions
sim2l.deploy_simulation(
    notebook="sim_v1.ipynb",
    name="my_sim",
    version="1.0.0"
)

sim2l.deploy_simulation(
    notebook="sim_v2.ipynb",
    name="my_sim",
    version="2.0.0"
)

# Load specific version
sim_v1 = sim2l.load_simulation("my_sim", version="1.0.0")
sim_v2 = sim2l.load_simulation("my_sim", version="2.0.0")

# Load latest
sim_latest = sim2l.load_simulation("my_sim")
```

---

## Troubleshooting

### Magic Commands Not Found

**Error:** `UsageError: Cell magic %%sim2l_inputs not found`

**Solution:** Load the extension first:
```python
%load_ext sim2l.notebook
```

### File Not Found (in notebook)

**Error:** `FileNotFoundError: [Errno 2] No such file or directory: 'data.csv'`

**Solution:** Use absolute paths for input files:
```python
# GOOD
input_file = str(Path("data.csv").resolve())

# BAD
input_file = "data.csv"
```

### Outputs Not Saved

**Error:** `AttributeError: 'NoneType' object has no attribute 'temperature'`

**Solution:** Make sure `save_outputs()` is called in the notebook:
```python
sim2l.save_outputs(
    temperature=result_temp,
    # ... other outputs
)
```

### UNIQUE Constraint Error

**Error:** `UNIQUE constraint failed: outputs.execution_id, outputs.name`

**Solution:** This is fixed in the latest version. The code now checks for existing outputs before inserting.

---

## Performance Tips

1. **Enable Caching:**
   ```python
   executor = NotebookExecutor(cache=True)
   ```

2. **Use SQUID IDs for deduplication:**
   ```python
   # Same inputs = same SQUID = cached result
   result1 = sim.run(temp=300)
   result2 = sim.run(temp=300)  # ← Instant (cached)
   ```

3. **Store only metadata in database:**
   ```python
   # Store file paths, not contents
   sim2l.save_outputs(
       output_file="data.csv",  # Path only
       row_count=1000           # Metadata
   )
   ```

4. **Use background execution for long-running tasks:**
   ```python
   executor = NotebookExecutor(
       cache=True,
       copy_files=True
   )
   ```

---

## Best Practices

### ✅ DO:
- Use absolute paths for input files
- Load `%load_ext sim2l.notebook` first
- Call `save_outputs()` in every notebook
- Use semantic versioning (1.0.0, 1.1.0, 2.0.0)
- Enable caching for parameter sweeps
- Store file paths, not contents

### ❌ DON'T:
- Use relative paths for input files
- Skip loading the extension
- Forget to call `save_outputs()`
- Store large files in database
- Disable caching for repeated executions
- Hardcode database paths

---

## Example Comparison

| Feature | Thermal Example | File Processing Example |
|---------|----------------|------------------------|
| Input types | Number (with units), Integer | Text (file paths), Text (choices) |
| Output types | Number, Array, Image, Boolean | Text (file paths), Integer, Number |
| Use case | Scientific simulation | Data processing |
| Complexity | Medium (NumPy, matplotlib) | Low (pandas) |
| File I/O | Image output | CSV/JSON/TXT input/output |
| Duration | ~3s (500 iterations) | ~2s (50 rows) |

---

## Additional Resources

- **Main Documentation:** `../docs/`
- **Architecture:** `../docs/sim2l_architecture.md`
- **Code Structure:** `../docs/sim2l_code_structure.md`
- **Quick Reference:** `../docs/sim2l_quick_reference.md`

---

## Contributing Examples

To add a new example:

1. Create notebook: `my_example.ipynb`
2. Create usage script: `use_my_example.py`
3. Add documentation: `MY_EXAMPLE.md`
4. Test thoroughly
5. Update this README

---

## Summary

All examples are **production-ready** and demonstrate:

✅ Database-backed persistence
✅ SQUID-based caching
✅ File input/output handling
✅ Physical units support
✅ Complex type serialization
✅ NotebookExecutor integration
✅ Complete workflow from authoring → deployment → execution

Ready to build your own simulations with sim2l! 🚀
