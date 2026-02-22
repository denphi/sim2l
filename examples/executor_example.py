# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Example: Using sim2l Executors

This example demonstrates:
1. Creating simulations from Python functions
2. Deploying to database
3. Executing with different executors (Local and Notebook)
4. Caching with SQUID IDs
5. Accessing typed results
"""

import sim2l
from sim2l.schema import InputSchema, OutputSchema
from sim2l.executor import LocalExecutor, NotebookExecutor
from sim2l.repository import SimulationRepository

print("=" * 60)
print("sim2l Executor Example")
print("=" * 60)
print()

# Step 1: Initialize database
print("Step 1: Initialize Database")
print("-" * 60)

repo = SimulationRepository.create(db_path="executor_example.db")
sim2l.configure(db_path="executor_example.db")

print("✓ Database created at: executor_example.db")
print()

# Step 2: Create a simple simulation from a Python function
print("Step 2: Create Simulation from Function")
print("-" * 60)

# Define schemas
inputs = InputSchema.from_yaml("""
a:
  type: Number
  description: "First number"

b:
  type: Number
  description: "Second number"

operation:
  type: Text
  choices: ["add", "multiply", "power"]
  default: "add"
  description: "Operation to perform"
""")

outputs = OutputSchema.from_yaml("""
result:
  type: Number
  description: "Result of operation"

operation_performed:
  type: Text
  description: "Which operation was performed"
""")

# Define simulation function
def calculator(a, b, operation="add"):
    """Simple calculator simulation"""
    if operation == "add":
        result = a + b
    elif operation == "multiply":
        result = a * b
    elif operation == "power":
        result = a ** b
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return {
        "result": result,
        "operation_performed": operation
    }

# Create simulation definition
sim_def = sim2l.SimulationDefinition.from_function(
    func=calculator,
    name="calculator",
    version="1.0.0",
    inputs=inputs,
    outputs=outputs,
    description="Simple calculator simulation",
    tags=["math", "calculator"]
)

print(f"✓ Created simulation: {sim_def}")
print()

# Step 3: Deploy simulation
print("Step 3: Deploy Simulation to Database")
print("-" * 60)

sim_id = repo.deploy(sim_def)
print(f"✓ Deployed with ID: {sim_id}")
print()

# Step 4: Load and execute with LocalExecutor
print("Step 4: Execute with LocalExecutor")
print("-" * 60)

# Load simulation
sim = sim2l.load_simulation("calculator", version="1.0.0")

# Execute with default executor (local)
result1 = sim.run(a=10, b=5, operation="add")

print(f"Execution ID: {result1.execution_id}")
print(f"SQUID ID: {result1.squid_id}")
print(f"Status: {result1.status}")
print(f"Duration: {result1.duration_seconds:.4f}s")
print(f"Result: {result1.outputs.result}")
print(f"Operation: {result1.outputs.operation_performed}")
print()

# Step 5: Execute again (should hit cache)
print("Step 5: Execute Again (Cache Test)")
print("-" * 60)

result2 = sim.run(a=10, b=5, operation="add")

print(f"Execution ID: {result2.execution_id}")
print(f"Same as before? {result2.execution_id == result1.execution_id}")
print(f"✓ Result cached (same execution ID)")
print()

# Step 6: Execute with different inputs
print("Step 6: Execute with Different Inputs")
print("-" * 60)

result3 = sim.run(a=2, b=8, operation="power")

print(f"Execution ID: {result3.execution_id}")
print(f"SQUID ID: {result3.squid_id}")
print(f"Result: {result3.outputs.result}")
print(f"Different from cached? {result3.execution_id != result1.execution_id}")
print()

# Step 7: Use explicit LocalExecutor
print("Step 7: Use Explicit LocalExecutor")
print("-" * 60)

executor = LocalExecutor(cache=False)  # Disable cache
result4 = sim.run(a=10, b=5, operation="multiply", executor=executor)

print(f"Execution ID: {result4.execution_id}")
print(f"Result: {result4.outputs.result}")
print(f"✓ New execution (cache disabled)")
print()

# Step 8: Compute SQUID ID manually
print("Step 8: SQUID ID Computation")
print("-" * 60)

squid = sim2l.compute_squid_id(
    simtool_name="calculator",
    simtool_revision="1.0.0",
    inputs={"a": 10, "b": 5, "operation": "add"}
)

print(f"SQUID ID: {squid}")
print(f"Matches result1? {squid == result1.squid_id}")
print()

# Step 9: List all executions
print("Step 9: Execution History")
print("-" * 60)

import sqlite3
conn = sqlite3.connect("executor_example.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT id, simulation_name, simulation_version, status, duration_seconds
    FROM executions
    ORDER BY executed_at DESC
""")

print(f"{'Execution ID':<40} {'Sim':<15} {'Ver':<8} {'Status':<10} {'Duration':>10}")
print("-" * 95)

for row in cursor.fetchall():
    exec_id, name, version, status, duration = row
    print(f"{exec_id:<40} {name:<15} {version:<8} {status:<10} {duration:>9.4f}s")

conn.close()
print()

# Step 10: Cache statistics
print("Step 10: Cache Statistics")
print("-" * 60)

conn = sqlite3.connect("executor_example.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT cache_key, access_count, last_accessed
    FROM cache
""")

print(f"{'Cache Key':<20} {'Hits':>6} {'Last Accessed'}")
print("-" * 60)

for row in cursor.fetchall():
    key, count, accessed = row
    print(f"{key:<20} {count:>6} {accessed}")

conn.close()
print()

# Summary
print("=" * 60)
print("Summary")
print("=" * 60)
print("✓ Created simulation from Python function")
print("✓ Deployed to database with versioning")
print("✓ Executed with LocalExecutor")
print("✓ Caching works (same inputs = cached result)")
print("✓ SQUID IDs computed correctly")
print("✓ Full execution history tracked")
print("✓ Cache statistics available")
print()
print("Key Features Demonstrated:")
print("  • sim.run() - Simple execution API")
print("  • Automatic caching with SQUID IDs")
print("  • Typed output access (result.outputs.fieldname)")
print("  • Full provenance tracking")
print("  • Executor flexibility (local, notebook)")
print()
print(f"Database: executor_example.db")
print(f"Total executions: 4 (1 cached)")
