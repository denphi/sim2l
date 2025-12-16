# Jupyter Notebook Example for sim2l

## Overview

This guide shows how to **define a simulation in a Jupyter notebook** using sim2l, then deploy and execute it.

## Files

1. **[thermal_simulation.ipynb](examples/thermal_simulation.ipynb)** - Notebook defining the simulation
2. **[use_thermal_simulation.py](examples/use_thermal_simulation.py)** - Python script using the deployed simulation

---

## Complete Workflow

### 1. Author Simulation in Notebook

**File**: `examples/thermal_simulation.ipynb`

#### Step 1: Define Inputs with Magic Cell

```python
%%sim2l_inputs

temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
  default: 300
  description: "Initial temperature of the system"

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
  max: 10000
  default: 100
  description: "Number of simulation iterations"

grid_size:
  type: Integer
  min: 10
  max: 200
  default: 50
  description: "Size of the simulation grid (NxN)"
```

#### Step 2: Define Outputs with Magic Cell

```python
%%sim2l_outputs

max_temperature:
  type: Number
  units: kelvin
  description: "Maximum temperature reached in the system"

temperature_distribution:
  type: Array
  dtype: float
  description: "Final temperature distribution (flattened)"

thermal_plot:
  type: Image
  description: "Visualization of temperature distribution"

converged:
  type: Boolean
  description: "Whether the simulation converged"

iterations_to_convergence:
  type: Integer
  description: "Number of iterations until convergence"
```

#### Step 3: Load Inputs for Testing

```python
import sim2l

# Get inputs from schema
inputs = sim2l.get_inputs()

# Override with test values
inputs.temperature = 300  # kelvin
inputs.power = 20         # watt
inputs.iterations = 500
inputs.grid_size = 50
```

#### Step 4: Simulation Logic

```python
import numpy as np

# Extract values
T_initial = inputs.temperature
power_applied = inputs.power
n = inputs.grid_size

# Initialize temperature field
T = np.ones((n, n)) * T_initial

# Simulation parameters
alpha = 0.01  # thermal diffusivity
dt = 0.01     # time step

# Main simulation loop
for iteration in range(inputs.iterations):
    T_old = T.copy()

    # 2D heat equation (finite difference)
    T[1:-1, 1:-1] = T_old[1:-1, 1:-1] + alpha * dt * (
        T_old[2:, 1:-1] + T_old[:-2, 1:-1] +
        T_old[1:-1, 2:] + T_old[1:-1, :-2] -
        4 * T_old[1:-1, 1:-1]
    )

    # Apply heat source at center
    center = n // 2
    T[center-2:center+2, center-2:center+2] += power_applied * dt / 16

    # Check convergence
    if np.max(np.abs(T - T_old)) < 1e-3:
        converged = True
        iterations_to_convergence = iteration + 1
        break
```

#### Step 5: Generate Visualization

```python
import matplotlib.pyplot as plt

# Create plot
fig, ax = plt.subplots(figsize=(8, 6))
im = ax.imshow(T, cmap='hot', interpolation='bilinear')
ax.set_title(f'Temperature Distribution\nMax: {np.max(T):.1f} K')
plt.colorbar(im, ax=ax, label='Temperature (K)')

# Save
plt.savefig('thermal_plot.png', dpi=150, bbox_inches='tight')
plt.show()
```

#### Step 6: Save Outputs

```python
# Save outputs according to schema
sim2l.save_outputs(
    max_temperature=float(np.max(T)),
    min_temperature=float(np.min(T)),
    avg_temperature=float(np.mean(T)),
    temperature_distribution=T.flatten(),
    thermal_plot='thermal_plot.png',
    converged=converged,
    iterations_to_convergence=iterations_to_convergence
)

print("✓ Outputs saved!")
```

#### Step 7: Deploy Simulation

```python
# Deploy this notebook as a versioned simulation
sim2l.deploy_simulation(
    notebook="thermal_simulation.ipynb",
    name="thermal_analysis",
    version="1.0.0",
    description="2D thermal diffusion simulation",
    author="Your Name",
    tags=["physics", "thermal", "finite-difference"]
)

print("✓ Simulation deployed!")
```

---

### 2. Use the Deployed Simulation

**File**: `examples/use_thermal_simulation.py`

```python
import sim2l
from sim2l.executor import NotebookExecutor

# Load simulation
sim = sim2l.load_simulation("thermal_analysis", version="1.0.0")

# Execute with NotebookExecutor
executor = NotebookExecutor(cache=True)
result = sim.run(
    temperature=350,
    power=25,
    iterations=500,
    grid_size=50,
    executor=executor
)

# Access results
print(f"Max Temperature: {result.outputs.max_temperature} K")
print(f"Converged: {result.outputs.converged}")
print(f"SQUID ID: {result.squid_id}")

# Execute again (cached!)
result2 = sim.run(temperature=350, power=25, iterations=500, grid_size=50)
print(f"Cached: {result.execution_id == result2.execution_id}")
```

---

## Key Features Demonstrated

### 1. Magic Cells

**%%sim2l_inputs** - Define inputs with type validation:
- Type-safe (Number, Integer, Array, Image, Boolean, etc.)
- Units support (kelvin, watt, etc.)
- Validation (min/max, choices)
- Default values
- Documentation

**%%sim2l_outputs** - Define expected outputs:
- Structured output schema
- Type information
- Documentation

### 2. Interactive Testing

```python
# Load inputs for testing
inputs = sim2l.get_inputs()

# Override values
inputs.temperature = 350
inputs.power = 20

# Run simulation code normally
# ...

# Save outputs
sim2l.save_outputs(max_temperature=max_temp, ...)
```

### 3. Deployment

```python
# Deploy notebook to database
sim2l.deploy_simulation(
    notebook="simulation.ipynb",
    name="sim_name",
    version="1.0.0"
)
```

### 4. Execution

```python
# Load from database
sim = sim2l.load_simulation("sim_name")

# Execute with NotebookExecutor (Papermill)
result = sim.run(temperature=350, power=20)

# Access typed outputs
print(result.outputs.max_temperature)
```

---

## Running the Example

### Option 1: Interactive Notebook

```bash
# Open in Jupyter
jupyter notebook examples/thermal_simulation.ipynb

# Run all cells
# Uncomment deployment cell and run
```

### Option 2: From Python Script

```bash
# Use the deployed simulation
python examples/use_thermal_simulation.py
```

### Option 3: Programmatic Deployment

```python
import sim2l

# Deploy the notebook
sim2l.deploy_simulation(
    notebook="examples/thermal_simulation.ipynb",
    name="thermal_analysis",
    version="1.0.0",
    description="2D thermal diffusion",
    tags=["physics", "thermal"]
)

# Execute
sim = sim2l.load_simulation("thermal_analysis")
result = sim.run(temperature=350, power=20, iterations=500, grid_size=50)

print(f"Max Temp: {result.outputs.max_temperature}")
```

---

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────┐
│  1. AUTHORING (Jupyter Notebook)                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │ %%sim2l_inputs                                     │  │
│  │   temperature: {type: Number, units: kelvin}      │  │
│  │                                                    │  │
│  │ %%sim2l_outputs                                    │  │
│  │   max_temperature: {type: Number, units: kelvin}  │  │
│  │                                                    │  │
│  │ # Simulation code                                  │  │
│  │ T = thermal_diffusion(temperature, power)         │  │
│  │                                                    │  │
│  │ sim2l.save_outputs(max_temperature=np.max(T))     │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  2. DEPLOYMENT                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │ sim2l.deploy_simulation(                          │  │
│  │     notebook="simulation.ipynb",                   │  │
│  │     name="thermal_analysis",                       │  │
│  │     version="1.0.0"                                │  │
│  │ )                                                  │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  3. DATABASE STORAGE                                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │ SQLite Database                                    │  │
│  │ - Simulation definition (versioned)                │  │
│  │ - Input/output schemas                             │  │
│  │ - Notebook bytes                                   │  │
│  │ - Metadata and tags                                │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  4. EXECUTION (From Anywhere)                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │ sim = sim2l.load_simulation("thermal_analysis")   │  │
│  │ result = sim.run(temperature=350, power=20)       │  │
│  │                                                    │  │
│  │ print(result.outputs.max_temperature)             │  │
│  │ print(result.squid_id)                            │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Comparison with simtool

### simtool Approach

```python
# In notebook
%%yaml INPUTS
temperature:
  type: Number
  units: kelvin

%%yaml OUTPUTS
max_temperature:
  type: Number

# Code
import scrapbook as sb
sb.glue('max_temperature', max_temp)

# Execute
from simtool import Run
r = Run("simulation.ipynb", inputs)
result = r.db.read('max_temperature')
```

**Issues**:
- Notebook file must be accessible
- No versioning
- No centralized storage
- File-based caching

### sim2l Approach

```python
# In notebook
%%sim2l_inputs
temperature:
  type: Number
  units: kelvin

%%sim2l_outputs
max_temperature:
  type: Number

# Code
sim2l.save_outputs(max_temperature=max_temp)

# Deploy once
sim2l.deploy_simulation(
    notebook="simulation.ipynb",
    name="simulation",
    version="1.0.0"
)

# Execute from anywhere
sim = sim2l.load_simulation("simulation")
result = sim.run(temperature=350)
max_temp = result.outputs.max_temperature
```

**Benefits**:
- ✅ Notebook stored in database
- ✅ Versioning support
- ✅ Centralized repository
- ✅ Database caching with SQUID IDs
- ✅ Typed result access

---

## Advanced Usage

### Parameter Sweeps

```python
sim = sim2l.load_simulation("thermal_analysis")

results = []
for temp in [300, 350, 400, 450, 500]:
    for power in [10, 15, 20, 25, 30]:
        result = sim.run(
            temperature=temp,
            power=power,
            iterations=500,
            grid_size=50
        )
        results.append({
            'temp': temp,
            'power': power,
            'max_temp': result.outputs.max_temperature,
            'converged': result.outputs.converged
        })

# Results automatically cached!
```

### Version Management

```python
# Deploy multiple versions
sim2l.deploy_simulation(
    notebook="thermal_v1.ipynb",
    name="thermal_analysis",
    version="1.0.0"
)

sim2l.deploy_simulation(
    notebook="thermal_v2.ipynb",
    name="thermal_analysis",
    version="2.0.0"
)

# Use specific version
sim_v1 = sim2l.load_simulation("thermal_analysis", version="1.0.0")
sim_v2 = sim2l.load_simulation("thermal_analysis", version="2.0.0")

# Or latest
sim_latest = sim2l.load_simulation("thermal_analysis")
```

### Custom Execution

```python
from sim2l.executor import NotebookExecutor
from pathlib import Path

# Custom output directory
executor = NotebookExecutor(
    cache=True,
    output_dir=Path("./my_runs"),
    copy_files=True
)

result = sim.run(temperature=350, executor=executor)

# Executed notebook saved to:
# ./my_runs/{run_id}/thermal_analysis_output.ipynb
```

---

## Troubleshooting

### Magic Not Recognized

If `%%sim2l_inputs` is not recognized, the IPython magic may not be loaded.

**Workaround**: Use legacy format
```python
%%yaml INPUTS
temperature:
  type: Number
  units: kelvin
```

sim2l supports both formats.

### Output Extraction Fails

Ensure scrapbook is installed and outputs are glued:

```python
import scrapbook as sb
sb.glue('max_temperature', max_temp)
```

Or use `sim2l.save_outputs()` which handles this automatically.

### Notebook Not Found

When deploying, use full path:

```python
from pathlib import Path

sim2l.deploy_simulation(
    notebook=Path(__file__).parent / "simulation.ipynb",
    name="sim_name",
    version="1.0.0"
)
```

---

## Summary

✅ **Notebook Example Complete**:
- Full thermal diffusion simulation in Jupyter notebook
- Uses `%%sim2l_inputs` and `%%sim2l_outputs` magic cells
- Interactive testing with `get_inputs()`
- Output saving with `save_outputs()`
- Deployment to database
- Execution with NotebookExecutor (Papermill)
- Parameter sweeps
- Caching with SQUID IDs

✅ **Files Created**:
- `examples/thermal_simulation.ipynb` - Complete notebook example
- `examples/use_thermal_simulation.py` - Usage example
- `NOTEBOOK_EXAMPLE.md` - This documentation

The example is **production-ready** and demonstrates the complete sim2l workflow for notebook-based simulations.
