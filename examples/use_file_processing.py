"""Example: File Processing Simulation with File Input/Output

This example demonstrates:
1. Deploying a simulation that processes files
2. Executing with file inputs
3. Retrieving file outputs
4. Running with different processing modes
"""

import sim2l
from sim2l.repository import SimulationRepository
from sim2l.executor import NotebookExecutor
from pathlib import Path
import shutil

print("=" * 60)
print("File Processing Simulation Example")
print("=" * 60)
print()

# Step 1: Setup database
print("Step 1: Setup Database")
print("-" * 60)

# Clean up previous run
if Path("file_processing.db").exists():
    Path("file_processing.db").unlink()

repo = SimulationRepository.create(db_path="file_processing.db")
sim2l.configure(db_path="file_processing.db")
print("✓ Database created: file_processing.db")
print()

# Step 2: Deploy simulation
print("Step 2: Deploy File Processing Simulation")
print("-" * 60)

sim_id = sim2l.deploy_simulation(
    notebook="file_processing_simulation.ipynb",
    name="file_processor",
    version="1.0.0",
    description="File processing simulation with multiple modes",
    author="sim2l Examples",
    tags=["file-processing", "data-analysis", "pandas"]
)
print(f"✓ Deployed simulation with ID: {sim_id}")
print()

# Step 3: Load simulation
print("Step 3: Load Simulation")
print("-" * 60)

sim = sim2l.load_simulation("file_processor", version="1.0.0")
print(f"Loaded: {sim.name} v{sim.version}")
print(f"Description: {sim.description}")

print("\nInputs:")
for name, field in sim.inputs.items():
    print(f"  {name}: {field.type_name}")
    if field.description:
        print(f"    → {field.description}")

print("\nOutputs:")
for name, field in sim.outputs.items():
    print(f"  {name}: {field.type_name}")
    if field.description:
        print(f"    → {field.description}")
print()

# Step 4: Execute with different modes
print("Step 4: Execute Simulation with Different Modes")
print("-" * 60)

executor = NotebookExecutor(cache=True)

# Test 1: Summarize mode
print("\n[Test 1] Mode: summarize, Format: csv")

# Use absolute path for input file
input_file_path = str(Path("sample_data.csv").resolve())
print(f"Input file: {input_file_path}")

result1 = sim.run(
    input_file=input_file_path,
    processing_mode="summarize",
    output_format="csv",
    executor=executor
)

print(f"  Execution ID: {result1.execution_id}")
print(f"  SQUID ID: {result1.squid_id}")
print(f"  Status: {result1.status}")
print(f"  Duration: {result1.duration_seconds:.2f}s")

if result1.status == "completed":
    print(f"\n  Results:")
    print(f"    Output file: {result1.outputs.output_file}")
    print(f"    Summary report: {result1.outputs.summary_report}")
    print(f"    Rows processed: {result1.outputs.row_count}")
    print(f"    Processing time: {result1.outputs.processing_time:.2f}s")

    # Show the files were created
    if Path(result1.outputs.output_file).exists():
        print(f"    ✓ Output file exists ({Path(result1.outputs.output_file).stat().st_size} bytes)")
    if Path(result1.outputs.summary_report).exists():
        print(f"    ✓ Report file exists ({Path(result1.outputs.summary_report).stat().st_size} bytes)")

# Test 2: Transform mode
print("\n[Test 2] Mode: transform, Format: json")
result2 = sim.run(
    input_file=input_file_path,
    processing_mode="transform",
    output_format="json",
    executor=executor
)

print(f"  Execution ID: {result2.execution_id}")
print(f"  Status: {result2.status}")
print(f"  Duration: {result2.duration_seconds:.2f}s")

if result2.status == "completed":
    print(f"\n  Results:")
    print(f"    Output file: {result2.outputs.output_file}")
    print(f"    Rows processed: {result2.outputs.row_count}")
    print(f"    Processing time: {result2.outputs.processing_time:.2f}s")

# Test 3: Analyze mode
print("\n[Test 3] Mode: analyze, Format: txt")
result3 = sim.run(
    input_file=input_file_path,
    processing_mode="analyze",
    output_format="txt",
    executor=executor
)

print(f"  Execution ID: {result3.execution_id}")
print(f"  Status: {result3.status}")
print(f"  Duration: {result3.duration_seconds:.2f}s")

if result3.status == "completed":
    print(f"\n  Results:")
    print(f"    Output file: {result3.outputs.output_file}")
    print(f"    Rows processed: {result3.outputs.row_count}")

print()

# Step 5: Show file contents
print("Step 5: Display Generated Files")
print("-" * 60)

if result1.status == "completed":
    # Show summary report
    report_path = Path(result1.outputs.summary_report)
    if report_path.exists():
        print("\n[Summary Report from Test 1]")
        print("-" * 60)
        with open(report_path) as f:
            content = f.read()
            # Show first 500 characters
            print(content[:500])
            if len(content) > 500:
                print(f"\n... ({len(content) - 500} more characters)")

print()

# Step 6: View execution history
print("Step 6: Execution History")
print("-" * 60)

import sqlite3
conn = sqlite3.connect("file_processing.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT id, simulation_version, executed_at, duration_seconds, status, inputs
    FROM executions
    WHERE simulation_name = 'file_processor'
    ORDER BY executed_at DESC
""")

print(f"\n{'Execution ID':<40} {'Ver':<8} {'Duration':>10} {'Status':<10} {'Mode':<12}")
print("-" * 90)

for row in cursor.fetchall():
    exec_id, version, executed_at, duration, status, inputs_json = row
    import json
    inputs_dict = json.loads(inputs_json)
    mode = inputs_dict.get('processing_mode', 'unknown')
    print(f"{exec_id:<40} {version:<8} {duration:>9.2f}s {status:<10} {mode:<12}")

conn.close()
print()

# Step 7: Test caching
print("Step 7: Test Caching (Re-run with same inputs)")
print("-" * 60)

print("\nRe-running Test 1 with same parameters...")
result1_cached = sim.run(
    input_file=input_file_path,
    processing_mode="summarize",
    output_format="csv",
    executor=executor
)

print(f"  Original Execution ID: {result1.execution_id}")
print(f"  New Execution ID:      {result1_cached.execution_id}")
print(f"  Same SQUID ID? {result1.squid_id == result1_cached.squid_id}")
print(f"  Duration: {result1_cached.duration_seconds:.2f}s")
print()

# Summary
print("=" * 60)
print("Summary")
print("=" * 60)
print("✓ Deployed file processing simulation")
print("✓ Executed with 3 different processing modes:")
print("  - summarize (CSV output)")
print("  - transform (JSON output)")
print("  - analyze (TXT output)")
print("✓ All outputs saved to database")
print("✓ Generated files:")
print(f"  - Output files in various formats")
print(f"  - Summary reports")
print("✓ SQUID IDs enable result caching")
print()
print(f"Database: file_processing.db")
print(f"Total executions: 4")
print()
print("Key Features Demonstrated:")
print("  • File path inputs (CSV files)")
print("  • File path outputs (generated files)")
print("  • Multiple processing modes (choice parameter)")
print("  • Output format selection")
print("  • Database storage of file paths")
print("  • Execution tracking and caching")
