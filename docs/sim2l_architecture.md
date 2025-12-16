# sim2l Library Architecture

## Executive Summary

**sim2l** is a refactored, modular simulation framework that decouples simulation logic from Jupyter notebooks, enabling simulations to be versioned, deployed, and reused as standalone artifacts. Unlike simtool, which tightly couples execution and state to notebooks, sim2l treats notebooks as an authoring interface while storing all simulation definitions, executions, and results in a persistent database.

## Core Principles

1. **Notebook-Agnostic Design**: Notebooks are for authoring; the library is the execution engine
2. **Separation of Concerns**: Clear boundaries between definition, validation, execution, and storage
3. **Reproducibility**: All executions are auditable and reproducible
4. **Versioning**: Simulations are versioned artifacts that can evolve independently
5. **Reusability**: Once deployed, simulations can be invoked from any Python context
6. **Extensibility**: Pluggable backends for storage, execution, and workflow orchestration

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AUTHORING LAYER                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           Jupyter Notebook (Authoring Interface)              │  │
│  │  - Define inputs/outputs (YAML)                               │  │
│  │  - Write workflow code                                        │  │
│  │  - Test & validate locally                                    │  │
│  └────────────────────┬─────────────────────────────────────────┘  │
│                       │                                              │
│                       ▼                                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Simulation Definition API                        │  │
│  │  sim2l.define()  →  Creates SimulationDefinition             │  │
│  │  sim2l.deploy()  →  Stores to database as versioned artifact │  │
│  └────────────────────┬─────────────────────────────────────────┘  │
└────────────────────────┼─────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PERSISTENCE LAYER                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  Simulation Repository                        │  │
│  │  - SQLite Database (default)                                  │  │
│  │  - Stores: definitions, versions, parameters, results         │  │
│  │  - Pluggable backend (PostgreSQL, MongoDB, etc.)             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EXECUTION LAYER                                 │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           Simulation Runtime API                              │  │
│  │  sim = sim2l.load("my_simulation", version="1.2.0")          │  │
│  │  result = sim.run(param1=value1, param2=value2)              │  │
│  └────────────────────┬─────────────────────────────────────────┘  │
│                       │                                              │
│                       ▼                                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Workflow Executor                                │  │
│  │  - LocalExecutor (in-process)                                 │  │
│  │  - PapermillExecutor (notebook execution)                     │  │
│  │  - SubmitExecutor (HUB submission)                            │  │
│  │  - DAGExecutor (future: complex workflows)                    │  │
│  └────────────────────┬─────────────────────────────────────────┘  │
│                       │                                              │
│                       ▼                                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Result Storage                                   │  │
│  │  - Execution metadata (timestamp, inputs, version)            │  │
│  │  - Output artifacts (typed data, files, arrays, images)       │  │
│  │  - Provenance tracking                                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CONSUMER LAYER                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │     Any Python Context (Notebooks, Scripts, APIs)             │  │
│  │  - Load deployed simulations                                  │  │
│  │  - Override parameters                                        │  │
│  │  - Execute and retrieve results                               │  │
│  │  - Chain simulations (use outputs as inputs)                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Modules and Responsibilities

### 1. `sim2l.definition` - Simulation Definition

**Purpose**: Create and manage simulation definitions

**Key Classes**:
- `SimulationDefinition`: Container for simulation metadata, schema, and code
- `InputSchema`: Type-safe input parameter definitions
- `OutputSchema`: Expected output structure and types
- `WorkflowSpec`: Defines how inputs transform to outputs

**Responsibilities**:
- Parse YAML input/output schemas
- Validate schema correctness
- Extract workflow code from notebooks or Python modules
- Generate simulation metadata (name, version, description, dependencies)

**API Example**:
```python
from sim2l import SimulationDefinition, InputSchema, OutputSchema

# Define from notebook
sim_def = SimulationDefinition.from_notebook(
    "my_simulation.ipynb",
    name="thermal_analysis",
    version="1.0.0"
)

# Or define programmatically
sim_def = SimulationDefinition(
    name="thermal_analysis",
    version="1.0.0",
    inputs=InputSchema.from_yaml("inputs.yaml"),
    outputs=OutputSchema.from_yaml("outputs.yaml"),
    workflow=my_workflow_function
)
```

---

### 2. `sim2l.repository` - Persistence Layer

**Purpose**: Store and retrieve simulation artifacts from database

**Key Classes**:
- `SimulationRepository`: Main interface for database operations
- `StorageBackend`: Abstract base class for storage implementations
- `SQLiteBackend`: Default SQLite implementation
- `SimulationRecord`: ORM-like representation of stored simulation

**Responsibilities**:
- Store simulation definitions (versioned)
- Store execution results with full provenance
- Query simulations by name, version, tags
- Manage simulation lifecycle (publish, deprecate, delete)
- Handle large artifacts (files, arrays) via blob storage or file references

**API Example**:
```python
from sim2l import SimulationRepository

# Initialize repository
repo = SimulationRepository(db_path="~/.sim2l/simulations.db")

# Deploy a simulation
repo.deploy(sim_def)

# Load a simulation
sim = repo.load("thermal_analysis", version="1.0.0")

# List available simulations
sims = repo.list(tags=["physics", "thermal"])
```

---

### 3. `sim2l.schema` - Type System

**Purpose**: Define and validate input/output parameters

**Key Classes**:
- `Field`: Base class for all parameter types (inherits from simtool's `Params`)
- `Integer`, `Number`, `Text`, `Array`, `Image`, `Element`: Typed fields
- `Schema`: Collection of fields with validation
- `UnitRegistry`: Physical units support (using Pint)

**Responsibilities**:
- Parse YAML schema definitions
- Runtime type validation
- Unit conversion and validation
- Serialization/deserialization (JSON, pickle)
- Generate JSON Schema for API documentation

**Improvements over simtool**:
- Cross-field validation (e.g., min_temp < max_temp)
- Computed/derived fields
- Conditional fields (only required if another field is set)
- Better error messages

**API Example**:
```python
from sim2l.schema import Schema, Number, Integer, Text

schema = Schema.from_yaml("""
temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
  description: "Operating temperature"

iterations:
  type: Integer
  min: 1
  default: 100

material:
  type: Text
  choices: ["silicon", "germanium", "gaas"]
""")

# Validate inputs
params = schema.validate({
    "temperature": 300,
    "iterations": 50,
    "material": "silicon"
})
```

---

### 4. `sim2l.executor` - Execution Engine

**Purpose**: Execute simulation workflows

**Key Classes**:
- `Executor`: Abstract base class
- `LocalExecutor`: Run Python functions in-process
- `NotebookExecutor`: Execute notebooks via Papermill
- `SubmitExecutor`: Submit to HUB/cluster
- `ExecutionContext`: Manages execution environment and outputs

**Responsibilities**:
- Prepare execution environment
- Inject parameters
- Execute workflow
- Capture outputs and errors
- Handle caching
- Manage dependencies and file copying

**API Example**:
```python
from sim2l import load_simulation
from sim2l.executor import LocalExecutor, NotebookExecutor

# Load simulation
sim = load_simulation("thermal_analysis", version="1.0.0")

# Execute with local executor
executor = LocalExecutor(cache=True)
result = sim.run(
    temperature=350,
    iterations=200,
    executor=executor
)

# Or use notebook executor
executor = NotebookExecutor(venue="submit")
result = sim.run(temperature=350, executor=executor)
```

---

### 5. `sim2l.result` - Result Management

**Purpose**: Handle execution results

**Key Classes**:
- `ExecutionResult`: Container for outputs, metadata, and provenance
- `OutputData`: Type-safe output accessor
- `ArtifactStore`: Manage large files and blobs

**Responsibilities**:
- Store outputs to database
- Retrieve outputs with proper typing
- Handle file references (images, arrays, large data)
- Track execution metadata (timestamp, duration, executor used)
- Provide result comparison and diffing

**API Example**:
```python
# Result from execution
result = sim.run(temperature=350)

# Access outputs (typed)
print(result.outputs.energy)  # Returns Number with units
print(result.outputs.plot)    # Returns Image

# Metadata
print(result.execution_id)
print(result.timestamp)
print(result.inputs)  # Original inputs used

# Save to database
result.save()

# Load previous result
from sim2l import load_result
old_result = load_result(execution_id="abc-123")
```

---

### 6. `sim2l.workflow` - Workflow Orchestration (Future)

**Purpose**: Define complex multi-step workflows

**Key Classes**:
- `WorkflowGraph`: DAG of simulation steps
- `Step`: Individual workflow node
- `Dependency`: Edge connecting steps

**Responsibilities**:
- Chain multiple simulations
- Pass outputs as inputs between steps
- Parallel execution where possible
- Conditional branching
- Error handling and retries

**API Example** (Future):
```python
from sim2l.workflow import Workflow, Step

# Define multi-step workflow
workflow = Workflow("device_optimization")

# Add steps
step1 = Step("material_selection", sim="material_sim")
step2 = Step("thermal_analysis", sim="thermal_sim")
step3 = Step("optimization", sim="optimizer_sim")

# Define dependencies
workflow.add_step(step1)
workflow.add_step(step2, depends_on=[step1],
                  inputs={"temperature": step1.outputs.optimal_temp})
workflow.add_step(step3, depends_on=[step2])

# Execute workflow
result = workflow.run(initial_params={"material_type": "silicon"})
```

---

### 7. `sim2l.cli` - Command Line Interface

**Purpose**: Provide CLI for common operations

**Commands**:
```bash
# List available simulations
sim2l list

# Deploy a simulation from notebook
sim2l deploy my_simulation.ipynb --name thermal_analysis --version 1.0.0

# Run a simulation
sim2l run thermal_analysis --temperature 350 --iterations 100

# Show simulation details
sim2l info thermal_analysis

# Export simulation definition
sim2l export thermal_analysis --version 1.0.0 --output ./

# Import simulation
sim2l import thermal_analysis.sim2l
```

---

### 8. `sim2l.migration` - Migration Tools

**Purpose**: Migrate from simtool to sim2l

**Utilities**:
- Convert simtool notebooks to sim2l format
- Import existing run results
- Generate migration report

**API Example**:
```python
from sim2l.migration import migrate_notebook, import_runs

# Migrate notebook
migrate_notebook("old_simulation.ipynb", output="new_simulation.ipynb")

# Import historical runs
import_runs(
    simtool_cache_dir="~/data/.simtool_cache",
    sim_name="thermal_analysis"
)
```

---

## Database Schema

### Core Tables

#### `simulations`
Stores simulation definitions and metadata

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment ID |
| name | TEXT NOT NULL | Simulation name (unique with version) |
| version | TEXT NOT NULL | Semantic version (e.g., "1.2.0") |
| description | TEXT | Human-readable description |
| created_at | TIMESTAMP | When simulation was deployed |
| updated_at | TIMESTAMP | Last modification time |
| author | TEXT | Creator username |
| tags | TEXT | JSON array of tags |
| input_schema | TEXT | JSON representation of InputSchema |
| output_schema | TEXT | JSON representation of OutputSchema |
| workflow_type | TEXT | "notebook", "function", "dag" |
| workflow_data | BLOB | Serialized workflow (notebook bytes, pickled function, etc.) |
| dependencies | TEXT | JSON list of required packages |
| status | TEXT | "active", "deprecated", "archived" |

**Indexes**:
- `UNIQUE(name, version)`
- `INDEX(name)`
- `INDEX(status)`
- `INDEX(created_at)`

---

#### `executions`
Stores execution history and provenance

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | UUID execution ID |
| simulation_id | INTEGER | Foreign key to simulations.id |
| simulation_version | TEXT | Version used (denormalized for queries) |
| executed_at | TIMESTAMP | When execution started |
| duration_seconds | REAL | Execution time |
| executor_type | TEXT | "local", "notebook", "submit" |
| executor_config | TEXT | JSON executor configuration |
| inputs | TEXT | JSON serialized inputs |
| status | TEXT | "running", "completed", "failed", "cached" |
| error_message | TEXT | Error details if failed |
| cache_key | TEXT | Hash of inputs for cache lookup |
| user | TEXT | Username who executed |
| environment | TEXT | JSON environment info (Python version, platform, etc.) |

**Indexes**:
- `INDEX(simulation_id)`
- `INDEX(executed_at)`
- `INDEX(status)`
- `INDEX(cache_key)` (for fast cache lookups)

---

#### `outputs`
Stores execution outputs

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment ID |
| execution_id | TEXT | Foreign key to executions.id |
| name | TEXT | Output variable name |
| type | TEXT | Data type ("number", "array", "image", "text", etc.) |
| value | TEXT | JSON serialized value (for small data) |
| value_blob | BLOB | Binary data (for large arrays, pickled objects) |
| file_path | TEXT | File reference for very large outputs |
| units | TEXT | Physical units (if applicable) |
| metadata | TEXT | JSON additional metadata |

**Indexes**:
- `INDEX(execution_id, name)`
- `INDEX(execution_id)`

---

#### `artifacts`
Stores large binary artifacts (images, arrays, files)

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Content hash (SHA256) |
| execution_id | TEXT | Foreign key to executions.id |
| name | TEXT | Artifact name |
| content_type | TEXT | MIME type |
| size_bytes | INTEGER | File size |
| storage_type | TEXT | "blob", "file", "s3" |
| storage_path | TEXT | Path or URL to artifact |
| data | BLOB | Actual data (if storage_type="blob") |
| created_at | TIMESTAMP | When stored |

**Indexes**:
- `INDEX(execution_id)`
- `INDEX(id)` (hash lookup for deduplication)

---

#### `cache`
Cache mapping for fast lookup

| Column | Type | Description |
|--------|------|-------------|
| cache_key | TEXT PRIMARY KEY | Hash of (simulation_id + inputs) |
| execution_id | TEXT | Foreign key to executions.id |
| created_at | TIMESTAMP | When cached |
| last_accessed | TIMESTAMP | Last cache hit |
| access_count | INTEGER | Number of cache hits |

**Purpose**: Fast O(1) cache lookups without scanning executions table

---

#### `simulation_tags`
Many-to-many relationship for tags

| Column | Type | Description |
|--------|------|-------------|
| simulation_id | INTEGER | Foreign key to simulations.id |
| tag | TEXT | Tag name |

**Indexes**:
- `INDEX(tag)`
- `INDEX(simulation_id)`

---

### Database Initialization

```python
from sim2l.repository import SimulationRepository

# Create new database
repo = SimulationRepository.create(
    db_path="~/.sim2l/simulations.db",
    backend="sqlite"
)

# Or connect to existing
repo = SimulationRepository(db_path="~/.sim2l/simulations.db")
```

---

## YAML Schema Format

### Input Schema Example

```yaml
# inputs.yaml

# Scalar parameters
temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
  default: 300
  description: "Operating temperature of the device"

voltage:
  type: Number
  units: volt
  min: 0
  max: 100
  default: 5.0
  description: "Applied voltage"

iterations:
  type: Integer
  min: 1
  max: 10000
  default: 100
  description: "Number of simulation iterations"

# Text parameters
material:
  type: Text
  choices: ["silicon", "germanium", "gaas", "inp"]
  default: "silicon"
  description: "Semiconductor material"

notes:
  type: Text
  maxlen: 500
  optional: true
  description: "User notes about this run"

# Element (chemistry)
dopant:
  type: Element
  choices: ["P", "As", "Sb", "B", "Al", "Ga"]
  default: "P"
  description: "Dopant element"

# Arrays
mesh_points:
  type: Array
  shape: [null, 3]  # Nx3 array
  dtype: float
  optional: true
  description: "Custom mesh point coordinates"

# Images
reference_image:
  type: Image
  optional: true
  description: "Reference image for comparison"

# Nested structures
device_params:
  type: Dict
  schema:
    width:
      type: Number
      units: micrometer
      min: 0
    length:
      type: Number
      units: micrometer
      min: 0
    layers:
      type: Integer
      min: 1

# Conditional fields
use_advanced_solver:
  type: Boolean
  default: false

solver_tolerance:
  type: Number
  min: 1e-10
  max: 1e-3
  default: 1e-6
  required_if: "use_advanced_solver == true"
  description: "Solver convergence tolerance"
```

---

### Output Schema Example

```yaml
# outputs.yaml

# Scalar outputs
total_energy:
  type: Number
  units: electronvolt
  description: "Total energy of the system"

convergence_iterations:
  type: Integer
  description: "Number of iterations until convergence"

# Arrays
potential_distribution:
  type: Array
  dtype: float
  description: "Electric potential at each mesh point"

# Images
band_diagram:
  type: Image
  description: "Energy band diagram visualization"

# Complex outputs
carrier_density:
  type: Dict
  schema:
    electrons:
      type: Array
      dtype: float
    holes:
      type: Array
      dtype: float

# Lists
warnings:
  type: List
  item_type: Text
  description: "List of warnings generated during simulation"

# Status/metadata
success:
  type: Boolean
  description: "Whether simulation completed successfully"

error_message:
  type: Text
  optional: true
  description: "Error message if simulation failed"
```

---

## Example: Authoring Notebook Workflow

**File**: `thermal_analysis_authoring.ipynb`

### Cell 1: Setup and Imports

```python
import sim2l
from sim2l.schema import InputSchema, OutputSchema
import numpy as np
import matplotlib.pyplot as plt
```

---

### Cell 2: Define Inputs (YAML)

```python
%%sim2l_inputs

temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
  default: 300
  description: "Operating temperature"

power:
  type: Number
  units: watt
  min: 0
  max: 100
  default: 10
  description: "Applied power"

iterations:
  type: Integer
  min: 1
  default: 100
  description: "Number of iterations"
```

---

### Cell 3: Define Outputs (YAML)

```python
%%sim2l_outputs

max_temperature:
  type: Number
  units: kelvin
  description: "Maximum temperature reached"

temperature_distribution:
  type: Array
  dtype: float
  description: "Temperature at each point"

thermal_plot:
  type: Image
  description: "Visualization of temperature distribution"

converged:
  type: Boolean
  description: "Whether simulation converged"
```

---

### Cell 4: Load Input Parameters (for interactive testing)

```python
# When authoring, use test values
from sim2l import get_inputs

# This loads from the YAML schema above
inputs = get_inputs()

# You can override for testing
inputs.temperature = 350  # kelvin
inputs.power = 15  # watt
inputs.iterations = 50

print(f"Temperature: {inputs.temperature}")
print(f"Power: {inputs.power}")
print(f"Iterations: {inputs.iterations}")
```

---

### Cell 5: Simulation Logic

```python
# Main simulation code
def run_thermal_simulation(temperature, power, iterations):
    """Run thermal diffusion simulation"""

    # Initialize temperature field
    nx, ny = 50, 50
    T = np.ones((nx, ny)) * temperature.magnitude  # Convert from Pint Quantity

    # Apply heat source
    heat_source = power.magnitude / (nx * ny)

    # Diffusion parameters
    alpha = 0.01  # thermal diffusivity
    dx = 1.0
    dt = 0.01

    # Iterative solver
    converged = False
    for i in range(iterations):
        T_old = T.copy()

        # Laplacian (simple finite difference)
        T[1:-1, 1:-1] = T_old[1:-1, 1:-1] + alpha * dt / dx**2 * (
            T_old[2:, 1:-1] + T_old[:-2, 1:-1] +
            T_old[1:-1, 2:] + T_old[1:-1, :-2] -
            4 * T_old[1:-1, 1:-1]
        )

        # Add heat source in center
        T[nx//2-2:nx//2+2, ny//2-2:ny//2+2] += heat_source * dt

        # Check convergence
        if np.max(np.abs(T - T_old)) < 1e-3:
            converged = True
            print(f"Converged at iteration {i}")
            break

    return T, converged

# Run simulation
T_final, converged = run_thermal_simulation(
    inputs.temperature,
    inputs.power,
    inputs.iterations
)

max_temp = np.max(T_final)
print(f"Max temperature: {max_temp} K")
```

---

### Cell 6: Generate Outputs

```python
# Create visualization
fig, ax = plt.subplots(figsize=(8, 6))
im = ax.imshow(T_final, cmap='hot', interpolation='nearest')
ax.set_title(f"Temperature Distribution (max: {max_temp:.1f} K)")
plt.colorbar(im, ax=ax, label="Temperature (K)")
plt.savefig("thermal_plot.png", dpi=150, bbox_inches='tight')
plt.close()
```

---

### Cell 7: Save Outputs (using sim2l)

```python
from sim2l import save_outputs

# Save outputs according to schema
save_outputs(
    max_temperature=max_temp,  # Scalar
    temperature_distribution=T_final.flatten(),  # Array
    thermal_plot="thermal_plot.png",  # Image file
    converged=converged  # Boolean
)

print("Outputs saved successfully!")
```

---

### Cell 8: Deploy Simulation

```python
# After testing, deploy as versioned simulation
from sim2l import deploy_simulation

deploy_simulation(
    notebook="thermal_analysis_authoring.ipynb",
    name="thermal_analysis",
    version="1.0.0",
    description="2D thermal diffusion simulation",
    tags=["physics", "thermal", "finite-difference"],
    author="username"
)

print("Simulation deployed! Ready to use from other notebooks.")
```

---

## Example: Consumer Notebook Usage

**File**: `use_thermal_analysis.ipynb`

### Cell 1: Load and Inspect Simulation

```python
from sim2l import load_simulation, list_simulations

# See what's available
sims = list_simulations(tags=["thermal"])
for sim in sims:
    print(f"{sim.name} v{sim.version}: {sim.description}")

# Load specific simulation
sim = load_simulation("thermal_analysis", version="1.0.0")

# Inspect schema
print("Inputs:")
for name, field in sim.inputs.items():
    print(f"  {name}: {field.type} ({field.description})")

print("\nOutputs:")
for name, field in sim.outputs.items():
    print(f"  {name}: {field.type}")
```

---

### Cell 2: Run with Custom Parameters

```python
# Execute simulation with custom inputs
result = sim.run(
    temperature=350,  # kelvin (auto-converted to proper units)
    power=20,         # watt
    iterations=200
)

print(f"Execution ID: {result.execution_id}")
print(f"Status: {result.status}")
print(f"Duration: {result.duration_seconds:.2f}s")
```

---

### Cell 3: Access Results

```python
# Access typed outputs
max_temp = result.outputs.max_temperature
print(f"Max temperature: {max_temp}")  # Has units!

temp_dist = result.outputs.temperature_distribution
print(f"Temperature distribution shape: {temp_dist.shape}")

# Display image
from IPython.display import Image, display
display(result.outputs.thermal_plot)

# Check convergence
if result.outputs.converged:
    print("Simulation converged successfully")
else:
    print("Warning: did not converge")
```

---

### Cell 4: Run Parameter Sweep

```python
import pandas as pd

# Run multiple simulations with different parameters
results = []

for temp in [300, 350, 400, 450, 500]:
    for power in [5, 10, 15, 20]:
        result = sim.run(
            temperature=temp,
            power=power,
            iterations=100,
            cache=True  # Use cached results if available
        )

        results.append({
            'temperature': temp,
            'power': power,
            'max_temperature': result.outputs.max_temperature.magnitude,
            'converged': result.outputs.converged,
            'duration': result.duration_seconds
        })

# Analyze results
df = pd.DataFrame(results)
print(df)

# Plot
import matplotlib.pyplot as plt
pivot = df.pivot(index='temperature', columns='power', values='max_temperature')
pivot.plot(kind='line', marker='o', figsize=(10, 6))
plt.xlabel('Initial Temperature (K)')
plt.ylabel('Max Temperature (K)')
plt.title('Parameter Sweep Results')
plt.legend(title='Power (W)')
plt.grid(True)
plt.show()
```

---

### Cell 5: Compare with Previous Results

```python
from sim2l import load_result

# Load a previous execution
old_result = load_result(execution_id="abc-123-previous-run")

# Compare
print(f"Old max temp: {old_result.outputs.max_temperature}")
print(f"New max temp: {result.outputs.max_temperature}")

delta = result.outputs.max_temperature - old_result.outputs.max_temperature
print(f"Difference: {delta}")
```

---

### Cell 6: Chain Simulations

```python
# Use output from one simulation as input to another
thermal_result = sim.run(temperature=350, power=20, iterations=100)

# Load another simulation that needs temperature distribution as input
stress_sim = load_simulation("stress_analysis", version="1.0.0")

stress_result = stress_sim.run(
    temperature_field=thermal_result.outputs.temperature_distribution,
    material="silicon"
)

print(f"Max stress: {stress_result.outputs.max_stress}")
```

---

## Migration from simtool to sim2l

### Key Differences

| Aspect | simtool | sim2l |
|--------|---------|-------|
| **Source of Truth** | Notebook files | Database |
| **Execution** | Run class with venue parameter | Executor pattern with pluggable backends |
| **Caching** | File-based cache directory | Database with cache table |
| **Reusability** | Must reference notebook file | Load by name/version from database |
| **Versioning** | Not supported | Semantic versioning built-in |
| **Result Storage** | Scrapbook glue in notebook metadata | Dedicated database tables |
| **Dependency Handling** | FILES cell tag | Packaged with simulation definition |
| **API** | `Run(notebook, inputs, venue)` | `sim.run(**params, executor)` |

---

### Migration Steps

#### 1. Convert Notebooks

```bash
# Use migration tool
sim2l migrate convert old_simulation.ipynb --output new_simulation.ipynb
```

**Changes**:
- `%%yaml INPUTS` → `%%sim2l_inputs`
- `%%yaml OUTPUTS` → `%%sim2l_outputs`
- `sb.glue()` → `save_outputs()`
- Add deployment cell at end

#### 2. Deploy Converted Simulations

```python
from sim2l.migration import deploy_from_simtool_notebook

# Batch deploy
deploy_from_simtool_notebook(
    notebook="old_simulation.ipynb",
    name="simulation_name",
    version="1.0.0",  # Initial version
    repository="~/.sim2l/simulations.db"
)
```

#### 3. Import Historical Run Data (Optional)

```python
from sim2l.migration import import_simtool_cache

# Import cached results from simtool
import_simtool_cache(
    cache_dir="~/data/.simtool_cache",
    simulation_name="thermal_analysis",
    repository="~/.sim2l/simulations.db"
)
```

This populates the executions and outputs tables with historical data.

#### 4. Update Consumer Code

**Before (simtool)**:
```python
from simtool import Run, get_inputs

inputs = get_inputs("simulation.ipynb")
inputs.temperature = 350

r = Run("simulation.ipynb", inputs, venue='submit')
results = r.db.read('output_name')
```

**After (sim2l)**:
```python
from sim2l import load_simulation

sim = load_simulation("simulation", version="1.0.0")
result = sim.run(temperature=350, executor="submit")
output = result.outputs.output_name
```

---

### Backward Compatibility Mode

For gradual migration, sim2l can provide a compatibility shim:

```python
# Enable simtool compatibility
import sim2l.compat as simtool

# Old code still works
from simtool import Run
r = Run("simulation.ipynb", inputs)
```

Internally, this:
1. Auto-deploys the notebook as a sim2l simulation (if not already deployed)
2. Translates the API call to sim2l equivalents
3. Returns results in the old format

---

### Migration Checklist

- [ ] Install sim2l: `pip install sim2l`
- [ ] Initialize repository: `sim2l init`
- [ ] Identify simtool notebooks to migrate
- [ ] Convert notebooks: `sim2l migrate convert *.ipynb`
- [ ] Deploy converted simulations: `sim2l deploy <notebooks>`
- [ ] (Optional) Import historical cache data
- [ ] Update consumer notebooks/scripts
- [ ] Test migrated simulations
- [ ] Deprecate simtool notebooks
- [ ] Update documentation

---

## Extension Points

### Custom Executors

```python
from sim2l.executor import Executor

class KubernetesExecutor(Executor):
    """Execute simulations on Kubernetes cluster"""

    def execute(self, simulation, inputs):
        # Create K8s Job
        # Submit to cluster
        # Wait for completion
        # Retrieve results
        pass

# Register
sim2l.register_executor("kubernetes", KubernetesExecutor)

# Use
result = sim.run(param=value, executor="kubernetes")
```

---

### Custom Storage Backends

```python
from sim2l.repository import StorageBackend

class PostgreSQLBackend(StorageBackend):
    """Store simulations in PostgreSQL"""

    def deploy(self, simulation_def):
        # Insert into PostgreSQL
        pass

    def load(self, name, version):
        # Query and return
        pass

# Use
repo = SimulationRepository(
    backend=PostgreSQLBackend(connection_string="postgresql://...")
)
```

---

### Custom Field Types

```python
from sim2l.schema import Field

class MoleculeField(Field):
    """Custom field for molecular structures"""

    def validate(self, value):
        # Validate SMILES string or molecule object
        pass

    def serialize(self, value):
        # Convert to JSON-serializable format
        pass

    def deserialize(self, data):
        # Reconstruct molecule object
        pass

# Register
sim2l.register_field_type("Molecule", MoleculeField)

# Use in YAML
# molecule:
#   type: Molecule
#   description: "Molecular structure"
```

---

## Summary

**sim2l** transforms simtool from a notebook-centric execution framework into a robust, database-backed simulation platform where:

1. **Notebooks are authoring tools**, not the source of truth
2. **Simulations are versioned artifacts** stored in a database
3. **Execution is decoupled** from definition via pluggable executors
4. **Results are queryable and reusable** via a rich API
5. **Workflows can be chained** and orchestrated
6. **Migration from simtool is straightforward** via automated tools

This design enables:
- **Reproducibility**: Every execution is tracked with full provenance
- **Collaboration**: Simulations can be shared and reused across teams
- **Scalability**: Pluggable backends support growth (local → cluster → cloud)
- **Maintainability**: Clear separation of concerns and modular design
- **Extensibility**: Custom executors, storage, and field types

**Next Steps**: Implement core modules iteratively, starting with `schema` and `definition`, then `repository`, followed by `executor` and `result`.
