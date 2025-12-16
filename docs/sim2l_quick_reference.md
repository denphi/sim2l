# sim2l Quick Reference

## Side-by-Side Comparison: simtool vs sim2l

### Creating a Simulation

#### simtool
```python
# Create notebook with YAML cells
%%yaml INPUTS
temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000

%%yaml OUTPUTS
max_temp:
  type: Number
  units: kelvin

# Simulation code with scrapbook
import scrapbook as sb
# ... compute max_temp ...
sb.glue('max_temp', max_temp)
```

**Source of truth**: Notebook file on disk

---

#### sim2l
```python
# Create notebook with sim2l magic cells
%%sim2l_inputs
temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000

%%sim2l_outputs
max_temp:
  type: Number
  units: kelvin

# Simulation code with sim2l API
from sim2l import save_outputs
# ... compute max_temp ...
save_outputs(max_temp=max_temp)

# Deploy as versioned artifact
from sim2l import deploy_simulation
deploy_simulation(
    notebook="sim.ipynb",
    name="thermal_sim",
    version="1.0.0"
)
```

**Source of truth**: SQLite database

---

### Running a Simulation

#### simtool
```python
from simtool import Run, get_inputs

# Load inputs from notebook
inputs = get_inputs("simulation.ipynb")
inputs.temperature = 350

# Execute (requires notebook file)
r = Run("simulation.ipynb", inputs, venue='submit')

# Access results
result = r.db.read('max_temp')
```

**Requires**: Notebook file accessible

---

#### sim2l
```python
from sim2l import load_simulation

# Load from database (no notebook needed)
sim = load_simulation("thermal_sim", version="1.0.0")

# Execute with parameters
result = sim.run(temperature=350, executor='submit')

# Access typed outputs
max_temp = result.outputs.max_temp  # Has units!
```

**Requires**: Only database access

---

### Caching

#### simtool
```python
# File-based cache in ~/data/.simtool_cache
r = Run(notebook, inputs, cache=True)
# Cache key based on inputs hash
# Results copied from cache directory
```

**Location**: `~/data/.simtool_cache/` (file system)

---

#### sim2l
```python
# Database-backed cache
result = sim.run(temperature=350, cache=True)
# Cache key: hash(simulation_id + inputs)
# O(1) lookup in cache table
# Results loaded from database
```

**Location**: SQLite `cache` and `executions` tables

---

### Parameter Sweeps

#### simtool
```python
from simtool import Run, get_inputs

results = []
for temp in [300, 350, 400]:
    inputs = get_inputs("sim.ipynb")
    inputs.temperature = temp
    r = Run("sim.ipynb", inputs)
    results.append(r.db.read('max_temp'))
```

**Limitation**: Must reference notebook file each time

---

#### sim2l
```python
from sim2l import load_simulation

sim = load_simulation("thermal_sim")
results = []

for temp in [300, 350, 400]:
    result = sim.run(temperature=temp, cache=True)
    results.append(result.outputs.max_temp)

# Or use built-in parameter sweep
results = sim.sweep({
    'temperature': [300, 350, 400],
    'power': [10, 20]
})
```

**Benefit**: Load once, run many times

---

### Listing Available Simulations

#### simtool
```bash
# List notebooks in /apps/simtools/
ls /apps/simtools/

# Or check local directory
ls *.ipynb
```

**Limitation**: No centralized catalog

---

#### sim2l
```python
from sim2l import list_simulations

# List all simulations
sims = list_simulations()

# Filter by tags
thermal_sims = list_simulations(tags=['thermal'])

# Print catalog
for sim in sims:
    print(f"{sim['name']} v{sim['version']}: {sim['description']}")
```

```bash
# CLI
sim2l list
sim2l list --tags thermal
sim2l info thermal_sim
```

**Benefit**: Centralized, searchable catalog

---

### Versioning

#### simtool
```python
# No versioning support
# Must manually copy/rename notebooks
# cp simulation.ipynb simulation_v2.ipynb
```

**Limitation**: Manual version management

---

#### sim2l
```python
# Semantic versioning built-in
deploy_simulation(
    notebook="sim.ipynb",
    name="thermal_sim",
    version="1.0.0"
)

# Later: deploy updated version
deploy_simulation(
    notebook="sim_updated.ipynb",
    name="thermal_sim",
    version="1.1.0"
)

# Load specific version
sim_v1 = load_simulation("thermal_sim", version="1.0.0")
sim_v2 = load_simulation("thermal_sim", version="1.1.0")

# Or latest
sim = load_simulation("thermal_sim")  # Gets latest
```

**Benefit**: Full version history and rollback

---

### Result Provenance

#### simtool
```python
# Limited metadata in notebook
r = Run(notebook, inputs)
# Results stored in notebook metadata
# No execution history tracking
```

**Limitation**: No execution history database

---

#### sim2l
```python
result = sim.run(temperature=350)

# Full provenance
print(result.execution_id)          # UUID
print(result.timestamp)             # When executed
print(result.duration_seconds)      # How long
print(result.inputs)                # Exact inputs used
print(result.simulation_version)    # Which version
print(result.executor_type)         # How executed
print(result.environment)           # Python version, platform, etc.

# Load historical results
from sim2l import load_result
old_result = load_result(execution_id="abc-123")

# Query executions
results = sim.query_executions(
    date_range=("2025-01-01", "2025-12-31"),
    status="completed"
)
```

**Benefit**: Complete audit trail

---

### Sharing Simulations

#### simtool
```bash
# Share notebook file
cp simulation.ipynb /shared/location/
# Others must have access to same file path
```

**Limitation**: File-based sharing

---

#### sim2l
```bash
# Export simulation as portable package
sim2l export thermal_sim --version 1.0.0 --output thermal_sim.sim2l

# Share file (contains everything)
# thermal_sim.sim2l

# Import on another machine
sim2l import thermal_sim.sim2l

# Or share database
# Just copy ~/.sim2l/simulations.db
```

**Benefit**: Portable, self-contained artifacts

---

### Workflow Chaining

#### simtool
```python
# Manual chaining
r1 = Run("sim1.ipynb", inputs1)
result1 = r1.db.read('output1')

# Manually pass to next simulation
inputs2 = get_inputs("sim2.ipynb")
inputs2.field = result1
r2 = Run("sim2.ipynb", inputs2)
```

**Limitation**: Manual, error-prone

---

#### sim2l
```python
# Explicit chaining
sim1 = load_simulation("sim1")
result1 = sim1.run(param=value)

sim2 = load_simulation("sim2")
result2 = sim2.run(field=result1.outputs.output1)

# Or use workflow (future)
from sim2l.workflow import Workflow, Step

workflow = Workflow("analysis_pipeline")
step1 = Step("thermal", sim="thermal_sim")
step2 = Step("stress", sim="stress_sim")

workflow.add_step(step1)
workflow.add_step(step2, depends_on=[step1],
    inputs={'temp_field': step1.outputs.max_temp})

result = workflow.run(initial_params={'material': 'silicon'})
```

**Benefit**: Type-safe, validated chaining

---

## Quick Start Guide

### Installation

```bash
pip install sim2l

# Initialize database
sim2l init
```

### Author a Simulation

```python
# In Jupyter notebook
%%sim2l_inputs
voltage:
  type: Number
  units: volt
  min: 0
  max: 100

%%sim2l_outputs
current:
  type: Number
  units: ampere

# Simulation code
voltage_val = voltage.magnitude
current_val = voltage_val / resistance

# Save outputs
from sim2l import save_outputs
save_outputs(current=current_val)

# Deploy
from sim2l import deploy_simulation
deploy_simulation(
    notebook="ohms_law.ipynb",
    name="ohms_law",
    version="1.0.0",
    description="Calculate current from voltage using Ohm's law",
    tags=["physics", "electronics"]
)
```

### Use a Simulation

```python
# In any Python environment
from sim2l import load_simulation

sim = load_simulation("ohms_law")
result = sim.run(voltage=5.0, resistance=100)

print(f"Current: {result.outputs.current} A")
```

### Browse Available Simulations

```bash
# CLI
sim2l list
sim2l info ohms_law
sim2l run ohms_law --voltage 5.0 --resistance 100
```

```python
# Python API
from sim2l import list_simulations

for sim in list_simulations():
    print(f"{sim['name']} v{sim['version']}")
    print(f"  {sim['description']}")
    print(f"  Tags: {', '.join(sim['tags'])}")
    print()
```

### Migrate from simtool

```bash
# Convert notebook
sim2l migrate convert old_simulation.ipynb

# Deploy converted simulation
sim2l deploy old_simulation.ipynb --name my_sim --version 1.0.0

# Import historical cache data
sim2l migrate import-cache ~/data/.simtool_cache --sim my_sim
```

---

## API Cheat Sheet

### Core Functions

```python
# Repository operations
from sim2l import (
    deploy_simulation,      # Deploy notebook as simulation
    load_simulation,        # Load simulation by name/version
    list_simulations,       # List available simulations
    load_result,           # Load historical execution result
)

# Notebook helpers
from sim2l import (
    get_inputs,            # Get input schema for authoring
    save_outputs,          # Save outputs in notebook
)

# Migration
from sim2l.migration import (
    migrate_notebook,      # Convert simtool notebook
    import_simtool_cache, # Import historical data
)

# Configuration
from sim2l import configure, get_config
configure(
    db_path="~/.sim2l/simulations.db",
    cache_enabled=True,
    default_executor="local"
)
```

### Schema Types

```python
from sim2l.schema import (
    Integer,    # Integer with min/max
    Number,     # Float with units, min/max
    Text,       # String with choices, maxlen
    Array,      # NumPy array with dtype, shape
    Image,      # PIL Image
    Element,    # Chemical element (via mendeleev)
    Boolean,    # True/False
    List,       # List of items
    Dict,       # Nested dictionary
)
```

### Executors

```python
from sim2l.executor import (
    LocalExecutor,      # In-process Python function
    NotebookExecutor,   # Jupyter notebook via Papermill
    SubmitExecutor,     # HUB submit system
)

# Use executor
from sim2l import load_simulation
sim = load_simulation("my_sim")

# Option 1: Specify executor instance
executor = NotebookExecutor(venue='submit')
result = sim.run(param=value, executor=executor)

# Option 2: Specify executor type
result = sim.run(param=value, executor='submit')

# Option 3: Use default (configured globally)
result = sim.run(param=value)
```

---

## Database Queries

### Direct SQLite Queries

```python
import sqlite3
from sim2l.config import get_config

db_path = get_config().db_path
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Find all versions of a simulation
cursor.execute("""
    SELECT version, created_at, status
    FROM simulations
    WHERE name = ?
    ORDER BY created_at DESC
""", ("thermal_sim",))

for version, created_at, status in cursor.fetchall():
    print(f"v{version} - {created_at} ({status})")

# Find most frequently run simulations
cursor.execute("""
    SELECT s.name, s.version, COUNT(*) as run_count
    FROM executions e
    JOIN simulations s ON e.simulation_id = s.id
    GROUP BY s.name, s.version
    ORDER BY run_count DESC
    LIMIT 10
""")

for name, version, count in cursor.fetchall():
    print(f"{name} v{version}: {count} runs")

conn.close()
```

---

## Configuration Files

### `~/.sim2l/config.json`

```json
{
  "db_path": "/home/user/.sim2l/simulations.db",
  "cache_enabled": true,
  "default_executor": "local",
  "artifact_storage": "database",
  "log_level": "INFO"
}
```

### Environment Variables

```bash
# Override config via environment
export SIM2L_DB_PATH=/custom/path/simulations.db
export SIM2L_CACHE_ENABLED=false
export SIM2L_DEFAULT_EXECUTOR=submit
export SIM2L_LOG_LEVEL=DEBUG
```

---

## Common Patterns

### Pattern 1: Parameter Sweep

```python
import pandas as pd
from sim2l import load_simulation

sim = load_simulation("thermal_sim")

results = []
for temp in range(300, 501, 50):
    for power in [5, 10, 15, 20]:
        result = sim.run(
            temperature=temp,
            power=power,
            cache=True
        )
        results.append({
            'temperature': temp,
            'power': power,
            'max_temp': result.outputs.max_temperature.magnitude,
            'execution_id': result.execution_id
        })

df = pd.DataFrame(results)
print(df)
```

### Pattern 2: Comparing Versions

```python
from sim2l import load_simulation

sim_v1 = load_simulation("thermal_sim", version="1.0.0")
sim_v2 = load_simulation("thermal_sim", version="2.0.0")

params = {'temperature': 350, 'power': 20}

result_v1 = sim_v1.run(**params)
result_v2 = sim_v2.run(**params)

print(f"v1.0.0: {result_v1.outputs.max_temperature}")
print(f"v2.0.0: {result_v2.outputs.max_temperature}")
print(f"Difference: {result_v2.outputs.max_temperature - result_v1.outputs.max_temperature}")
```

### Pattern 3: Batch Processing

```python
from sim2l import load_simulation
import multiprocessing

sim = load_simulation("analysis_sim")

def run_one(params):
    return sim.run(**params)

param_sets = [
    {'material': 'silicon', 'temp': 300},
    {'material': 'germanium', 'temp': 350},
    {'material': 'gaas', 'temp': 400},
]

# Parallel execution
with multiprocessing.Pool(4) as pool:
    results = pool.map(run_one, param_sets)

for params, result in zip(param_sets, results):
    print(f"{params} → {result.outputs}")
```

---

## Troubleshooting

### Common Issues

**Issue**: `SimulationNotFoundError: 'my_sim' not found in repository`

**Solution**:
```python
# Check available simulations
from sim2l import list_simulations
print(list_simulations())

# Deploy if missing
from sim2l import deploy_simulation
deploy_simulation(notebook="my_sim.ipynb", name="my_sim", version="1.0.0")
```

---

**Issue**: `ValidationError: Required field 'temperature' is missing`

**Solution**:
```python
# Check input schema
sim = load_simulation("thermal_sim")
for name, field in sim.inputs.items():
    print(f"{name}: {field.type} (required: {not field.optional})")

# Provide all required fields
result = sim.run(temperature=350, power=20, iterations=100)
```

---

**Issue**: Cache not working / always re-executing

**Solution**:
```python
# Check cache configuration
from sim2l import get_config
print(f"Cache enabled: {get_config().cache_enabled}")

# Enable cache
from sim2l import configure
configure(cache_enabled=True)

# Or per-run
result = sim.run(param=value, cache=True)
```

---

**Issue**: Units error: `DimensionalityError`

**Solution**:
```python
# sim2l uses Pint for units
# Ensure compatible units

# This works (both are temperature)
result = sim.run(temperature=350)  # kelvin (default unit in schema)
result = sim.run(temperature=76.85)  # Will convert if schema has units=kelvin

# Explicit unit specification
from pint import UnitRegistry
ureg = UnitRegistry()
result = sim.run(temperature=350 * ureg.kelvin)
result = sim.run(temperature=76.85 * ureg.celsius)  # Auto-converts
```

---

This quick reference provides practical, side-by-side comparisons and common usage patterns for transitioning from simtool to sim2l.
