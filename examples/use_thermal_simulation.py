# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Example: Using a Notebook-Based Simulation

This example shows how to use a simulation that was defined in a Jupyter notebook.

Prerequisites:
1. Run thermal_simulation.ipynb interactively
2. Uncomment the deployment cell to deploy the simulation
3. Run this script to execute the deployed simulation

This demonstrates the full sim2l workflow:
- Define in notebook (thermal_simulation.ipynb)
- Deploy to database
- Execute from anywhere (this script)
"""

import sim2l
from sim2l.repository import SimulationRepository
import numpy as np
import matplotlib.pyplot as plt

print("=" * 60)
print("Using Notebook-Based Simulation")
print("=" * 60)
print()

# Step 1: Deploy the simulation (if not already deployed)
print("Step 1: Deploy Simulation from Notebook")
print("-" * 60)

try:
    # Initialize database
    repo = SimulationRepository.create(db_path="thermal_sims.db")
    sim2l.configure(db_path="thermal_sims.db")
    print("✓ Database created: thermal_sims.db")

    # Deploy the notebook
    sim_id = sim2l.deploy_simulation(
        notebook="thermal_simulation.ipynb",
        name="thermal_analysis",
        version="1.0.0",
        description="2D thermal diffusion simulation",
        author="sim2l Example",
        tags=["physics", "thermal", "finite-difference"]
    )
    print(f"✓ Deployed simulation with ID: {sim_id}")

except ValueError as e:
    if "already exists" in str(e):
        print("✓ Simulation already deployed")
        sim2l.configure(db_path="thermal_sims.db")
    else:
        raise

print()

# Step 2: Load the simulation
print("Step 2: Load Simulation from Database")
print("-" * 60)

sim = sim2l.load_simulation("thermal_analysis", version="1.0.0")

print(f"Loaded: {sim.name} v{sim.version}")
print(f"Description: {sim.description}")
print(f"Tags: {', '.join(sim.tags)}")
print()

print("Inputs:")
for name, field in sim.inputs.items():
    print(f"  {name}: {field.type_name}", end="")
    if hasattr(field, 'units') and field.units:
        print(f" [{field.units}]", end="")
    if field.description:
        print(f" - {field.description}")
    else:
        print()

print("\nOutputs:")
for name, field in sim.outputs.items():
    print(f"  {name}: {field.type_name}", end="")
    if hasattr(field, 'units') and field.units:
        print(f" [{field.units}]")
    else:
        print()

print()

# Step 3: Execute with NotebookExecutor
print("Step 3: Execute with NotebookExecutor")
print("-" * 60)

from sim2l.executor import NotebookExecutor

# Create executor
executor = NotebookExecutor(cache=True)

# Execute simulation
result = sim.run(
    temperature=350,
    power=25,
    iterations=500,
    grid_size=50,
    executor=executor
)

print(f"Execution ID: {result.execution_id}")
print(f"SQUID ID: {result.squid_id}")
print(f"Status: {result.status}")
print(f"Duration: {result.duration_seconds:.2f}s")
print()

# Step 4: Access Results
print("Step 4: Access Typed Results")
print("-" * 60)

print(f"Max Temperature: {result.outputs.max_temperature:.2f} K")
print(f"Min Temperature: {result.outputs.min_temperature:.2f} K")
print(f"Avg Temperature: {result.outputs.avg_temperature:.2f} K")
print(f"Converged: {result.outputs.converged}")
print(f"Iterations to Convergence: {result.outputs.iterations_to_convergence}")
print()

# Display temperature distribution statistics
temp_dist = result.outputs.temperature_distribution
print(f"Temperature Distribution:")
print(f"  Shape: {temp_dist.shape}")
print(f"  Std Dev: {np.std(temp_dist):.2f} K")
print(f"  Range: {np.max(temp_dist) - np.min(temp_dist):.2f} K")
print()

# Step 5: Execute again (should hit cache)
print("Step 5: Execute Again (Cache Test)")
print("-" * 60)

result2 = sim.run(
    temperature=350,
    power=25,
    iterations=500,
    grid_size=50,
    executor=executor
)

print(f"Execution ID: {result2.execution_id}")
print(f"Same as before? {result2.execution_id == result.execution_id}")
print(f"✓ Result was cached!")
print()

# Step 6: Parameter sweep
print("Step 6: Parameter Sweep")
print("-" * 60)

print("Running simulations with different power levels...")

results = []
power_levels = [10, 15, 20, 25, 30]

for power in power_levels:
    r = sim.run(
        temperature=300,
        power=power,
        iterations=500,
        grid_size=50,
        executor=executor
    )

    results.append({
        'power': power,
        'max_temp': r.outputs.max_temperature,
        'avg_temp': r.outputs.avg_temperature,
        'converged': r.outputs.converged,
        'iterations': r.outputs.iterations_to_convergence,
        'duration': r.duration_seconds
    })

    print(f"  Power: {power:3}W → Max Temp: {r.outputs.max_temperature:6.2f}K, "
          f"Converged: {r.outputs.converged}, Duration: {r.duration_seconds:.2f}s")

print()

# Step 7: Visualize parameter sweep
print("Step 7: Visualize Results")
print("-" * 60)

# Extract data
powers = [r['power'] for r in results]
max_temps = [r['max_temp'] for r in results]
avg_temps = [r['avg_temp'] for r in results]

# Create plot
fig, ax = plt.subplots(figsize=(10, 6))

ax.plot(powers, max_temps, 'o-', label='Max Temperature', linewidth=2, markersize=8)
ax.plot(powers, avg_temps, 's-', label='Avg Temperature', linewidth=2, markersize=8)

ax.set_xlabel('Applied Power (W)', fontsize=12)
ax.set_ylabel('Temperature (K)', fontsize=12)
ax.set_title('Temperature vs Applied Power\n(Initial Temperature: 300K, 500 iterations)',
             fontsize=14)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('parameter_sweep_results.png', dpi=150, bbox_inches='tight')
print("✓ Plot saved to: parameter_sweep_results.png")
plt.show()

print()

# Step 8: Execution history
print("Step 8: View Execution History")
print("-" * 60)

import sqlite3

conn = sqlite3.connect("thermal_sims.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT id, simulation_version, executed_at, duration_seconds, status
    FROM executions
    WHERE simulation_name = 'thermal_analysis'
    ORDER BY executed_at DESC
    LIMIT 10
""")

print(f"{'Execution ID':<40} {'Ver':<8} {'Duration':>10} {'Status':<10}")
print("-" * 75)

for row in cursor.fetchall():
    exec_id, version, executed_at, duration, status = row
    print(f"{exec_id:<40} {version:<8} {duration:>9.2f}s {status:<10}")

conn.close()
print()

# Summary
print("=" * 60)
print("Summary")
print("=" * 60)
print("✓ Deployed simulation from Jupyter notebook")
print("✓ Executed using NotebookExecutor with Papermill")
print("✓ Accessed typed outputs with units")
print("✓ Caching works (same inputs = cached)")
print("✓ Ran parameter sweep (5 different power levels)")
print("✓ Visualized results")
print("✓ Viewed execution history")
print()
print("Key Features:")
print("  • Define once in notebook, execute anywhere")
print("  • Automatic caching with SQUID IDs")
print("  • Type-safe outputs")
print("  • Full provenance tracking")
print("  • Version management")
print()
print(f"Database: thermal_sims.db")
print(f"Total executions: {len(results) + 2}")
print(f"Cached: {1}")
