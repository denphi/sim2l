# Setting Up sim2l in Jupyter Notebooks

## Quick Start

Add this cell at the **very beginning** of your notebook:

```python
# Load sim2l IPython extension
%load_ext sim2l.notebook

import sim2l
print(f"sim2l version: {sim2l.__version__}")
print("✓ sim2l magics loaded")
```

This enables the `%%sim2l_inputs` and `%%sim2l_outputs` magic commands.

---

## Complete Setup Example

### Cell 1: Load Extension

```python
# Load sim2l extension for magic commands
%load_ext sim2l.notebook
```

**Output**: `sim2l magics loaded. Use %%sim2l_inputs and %%sim2l_outputs`

---

### Cell 2: Define Inputs

```python
%%sim2l_inputs

temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
  default: 300
  description: "Initial temperature"

power:
  type: Number
  units: watt
  min: 0
  max: 100
  default: 10
  description: "Applied power"
```

**Output**: `✓ Defined 2 input parameters`

---

### Cell 3: Define Outputs

```python
%%sim2l_outputs

max_temperature:
  type: Number
  units: kelvin
  description: "Maximum temperature"

converged:
  type: Boolean
  description: "Whether simulation converged"
```

**Output**: `✓ Defined 2 output parameters`

---

### Cell 4: Get Inputs for Testing

```python
import sim2l

# Get inputs (loads from %%sim2l_inputs cell)
inputs = sim2l.get_inputs()

# Override for testing
inputs.temperature = 350
inputs.power = 20

print(f"Temperature: {inputs.temperature} K")
print(f"Power: {inputs.power} W")
```

---

### Cell 5: Your Simulation Code

```python
import numpy as np

# Your simulation logic here
T = run_simulation(inputs.temperature, inputs.power)
max_temp = np.max(T)
converged = True
```

---

### Cell 6: Save Outputs

```python
# Save outputs (matches %%sim2l_outputs schema)
sim2l.save_outputs(
    max_temperature=max_temp,
    converged=converged
)

print("✓ Outputs saved!")
```

---

### Cell 7: Deploy (Optional)

```python
# Deploy to database
sim2l.deploy_simulation(
    notebook="my_simulation.ipynb",
    name="my_sim",
    version="1.0.0",
    description="My simulation",
    tags=["physics"]
)

print("✓ Deployed!")
```

---

## Usage Without Extension (Alternative)

If you can't load the extension, you can define schemas programmatically:

```python
import sim2l
from sim2l.schema import InputSchema, OutputSchema

# Define inputs
inputs = InputSchema.from_yaml("""
temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
""")

# Define outputs
outputs = OutputSchema.from_yaml("""
max_temperature:
  type: Number
  units: kelvin
""")

# Your simulation code
# ...

# Deploy
from sim2l import SimulationDefinition
sim_def = SimulationDefinition.from_function(
    func=my_simulation_function,
    name="my_sim",
    version="1.0.0",
    inputs=inputs,
    outputs=outputs
)

from sim2l.repository import SimulationRepository
repo = SimulationRepository()
repo.deploy(sim_def)
```

---

## Troubleshooting

### "sim2l magics not found"

Make sure you've installed sim2l:
```bash
cd sim2l
pip install -e .
```

### "No module named 'IPython'"

Install IPython:
```bash
pip install ipython jupyter
```

### "get_inputs() failed"

Make sure you:
1. Loaded the extension: `%load_ext sim2l.notebook`
2. Defined inputs: `%%sim2l_inputs` cell
3. Call `get_inputs()` **after** the input definition cell

---

## Complete Notebook Template

```python
# Cell 1: Setup
%load_ext sim2l.notebook
import sim2l

# Cell 2: Inputs
%%sim2l_inputs
temperature:
  type: Number
  units: kelvin
  default: 300

# Cell 3: Outputs
%%sim2l_outputs
result:
  type: Number

# Cell 4: Load inputs
inputs = sim2l.get_inputs()
inputs.temperature = 350

# Cell 5: Simulation
result = inputs.temperature * 2

# Cell 6: Save
sim2l.save_outputs(result=result)

# Cell 7: Deploy
sim2l.deploy_simulation(
    notebook="template.ipynb",
    name="template",
    version="1.0.0"
)
```

---

## Key Points

✓ **Load extension first**: `%load_ext sim2l.notebook`
✓ **Magic cells**: Use `%%sim2l_inputs` and `%%sim2l_outputs`
✓ **Get inputs**: Call `sim2l.get_inputs()` after defining them
✓ **Save outputs**: Call `sim2l.save_outputs(**outputs)`
✓ **Deploy**: Optional, makes simulation reusable

The magic commands make notebook authoring much cleaner than manually creating schemas!
