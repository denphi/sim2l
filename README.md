# sim2l - Simulation Framework with Database-Backed Persistence

sim2l is a modular, notebook-agnostic library for defining, deploying, and executing simulations as versioned, reusable artifacts.

## Features

- **Database-backed persistence**: All simulations stored in SQLite with full versioning
- **Notebook-friendly authoring**: Define simulations in Jupyter notebooks
- **Reusable artifacts**: Deploy once, execute anywhere
- **Type-safe schemas**: Comprehensive input/output validation with units support
- **Pluggable executors**: Local, notebook (Papermill), HUB submit, and extensible
- **Smart caching**: Automatic result caching based on inputs
- **Full provenance**: Track all executions with complete metadata

## Quick Start

### Installation

```bash
pip install sim2l
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

# Your simulation code
current_val = voltage.magnitude / resistance

# Save outputs
from sim2l import save_outputs
save_outputs(current=current_val)

# Deploy
from sim2l import deploy_simulation
deploy_simulation(
    notebook="ohms_law.ipynb",
    name="ohms_law",
    version="1.0.0"
)
```

### Use a Simulation

```python
from sim2l import load_simulation

sim = load_simulation("ohms_law")
result = sim.run(voltage=5.0, resistance=100)
print(f"Current: {result.outputs.current}")
```

## Documentation

See the `docs/` directory for:
- [Architecture](docs/sim2l_architecture.md)
- [Quick Reference](docs/sim2l_quick_reference.md)

## License

MIT License
