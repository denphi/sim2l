# File Processing Example - File Input/Output with NotebookExecutor

This example demonstrates how to create a sim2l simulation that processes files using file paths as inputs and outputs.

## Files

- **[file_processing_simulation.ipynb](file_processing_simulation.ipynb)** - Notebook defining the file processing simulation
- **[use_file_processing.py](use_file_processing.py)** - Python script that deploys and executes the simulation
- **[sample_data.csv](sample_data.csv)** - Sample input data file

## Overview

This example shows:

1. **File path inputs** - Using `Text` type fields to pass file paths
2. **File path outputs** - Returning paths to generated files
3. **Multiple processing modes** - Using choice parameters (summarize, transform, analyze)
4. **Different output formats** - CSV, JSON, TXT
5. **Database storage** - File paths stored in database, files remain in execution directory
6. **Caching** - Same inputs = same SQUID ID = cached results

## Quick Start

```bash
# Create sample data
python3 -c "
import pandas as pd
import numpy as np

np.random.seed(42)
data = {
    'temperature': np.random.uniform(20, 100, 50),
    'pressure': np.random.uniform(1, 10, 50),
    'flow_rate': np.random.uniform(0.1, 5.0, 50),
    'efficiency': np.random.uniform(0.6, 0.95, 50),
    'status': np.random.choice(['active', 'idle', 'maintenance'], 50)
}
pd.DataFrame(data).to_csv('sample_data.csv', index=False)
"

# Run the example
python3 use_file_processing.py
```

## How It Works

### 1. Define Input Schema

```python
%%sim2l_inputs

input_file:
  type: Text
  description: "Path to input data file (CSV format)"

processing_mode:
  type: Text
  choices: ["summarize", "transform", "analyze"]
  default: "summarize"
  description: "Processing mode to apply"

output_format:
  type: Text
  choices: ["csv", "json", "txt"]
  default: "csv"
  description: "Output file format"
```

**Key Points:**
- File paths are passed as `Text` type (not a special File type)
- The notebook receives the path as a string parameter
- Use absolute paths to avoid issues with working directory changes

### 2. Define Output Schema

```python
%%sim2l_outputs

output_file:
  type: Text
  description: "Path to generated output file"

summary_report:
  type: Text
  description: "Path to summary report file"

row_count:
  type: Integer
  description: "Number of rows processed"

processing_time:
  type: Number
  units: second
  description: "Time taken to process"
```

**Output Files:**
- The notebook generates files in its execution directory
- Relative paths are returned (e.g., "output.csv")
- Files can be found in the temp execution directory
- File paths are stored in the database

### 3. Process Files in Notebook

```python
# Read input file (absolute path passed as parameter)
df = pd.read_csv(input_file)

# Process based on mode
if processing_mode == "summarize":
    result_df = df.describe()
    # ... generate summary
elif processing_mode == "transform":
    # ... transform data
elif processing_mode == "analyze":
    # ... analyze data

# Generate output file
if output_format == "csv":
    result_df.to_csv("output.csv")
elif output_format == "json":
    result_df.to_json("output.json")
elif output_format == "txt":
    with open("output.txt", 'w') as f:
        f.write(result_df.to_string())

# Save outputs to database
sim2l.save_outputs(
    output_file=f"output.{output_format}",
    summary_report="summary_report.txt",
    row_count=int(len(df)),
    processing_time=float(processing_time)
)
```

### 4. Execute from Python

```python
import sim2l
from sim2l.executor import NotebookExecutor
from pathlib import Path

# Deploy simulation
sim2l.deploy_simulation(
    notebook="file_processing_simulation.ipynb",
    name="file_processor",
    version="1.0.0"
)

# Load and execute
sim = sim2l.load_simulation("file_processor")
executor = NotebookExecutor(cache=True)

# Use ABSOLUTE path for input file
input_file = str(Path("sample_data.csv").resolve())

result = sim.run(
    input_file=input_file,
    processing_mode="summarize",
    output_format="csv",
    executor=executor
)

# Access results
print(f"Status: {result.status}")
print(f"Output file: {result.outputs.output_file}")
print(f"Rows processed: {result.outputs.row_count}")
print(f"Processing time: {result.outputs.processing_time:.2f}s")
```

## Important Notes

### File Path Handling

1. **Input Files - Use Absolute Paths:**
   ```python
   # GOOD - Absolute path
   input_file = str(Path("data.csv").resolve())
   result = sim.run(input_file=input_file)

   # BAD - Relative path (won't work in temp directory)
   result = sim.run(input_file="data.csv")
   ```

2. **Output Files - Relative Paths OK:**
   ```python
   # In notebook - relative paths work fine
   df.to_csv("output.csv")
   sim2l.save_outputs(output_file="output.csv")
   ```

3. **Finding Generated Files:**
   ```python
   # Files are in the execution temp directory
   print(f"Execution directory: {result.execution_id}")
   # /var/folders/.../sim2l_runs/{run_id}/output.csv
   ```

### Database Storage

- **File paths** (strings) are stored in the `outputs` table
- **File contents** are NOT stored in database
- Generated files remain in the temp execution directory
- For permanent storage, copy files after execution:

```python
import shutil
from pathlib import Path

result = sim.run(...)
if result.status == "completed":
    # Copy output file to permanent location
    src = Path(result.outputs.output_file)
    dst = Path("./results") / src.name
    if src.exists():
        shutil.copy(src, dst)
```

## Example Output

```
Step 4: Execute Simulation with Different Modes
------------------------------------------------------------

[Test 1] Mode: summarize, Format: csv
Input file: /Users/.../sample_data.csv
  Execution ID: fb97b17b-efeb-4f01-9a96-c224632a8306
  SQUID ID: file_processor/1.0.0/f7f22042a84a63dfc7be09ec7ad43e006c9a931c
  Status: completed
  Duration: 2.51s

  Results:
    Output file: output.csv
    Summary report: summary_report.txt
    Rows processed: 50
    Processing time: 0.02 seconds

[Test 2] Mode: transform, Format: json
  Status: completed
  Duration: 1.95s
  Output file: output.json
  Rows processed: 50

[Test 3] Mode: analyze, Format: txt
  Status: completed
  Duration: 2.09s
  Output file: output.txt
  Rows processed: 50
```

## Database Schema

```sql
-- Outputs table stores file paths
SELECT execution_id, name, type, value
FROM outputs
WHERE execution_id = 'fb97b17b-efeb-4f01-9a96-c224632a8306';

-- Results:
-- output_file        | str    | "output.csv"
-- summary_report     | str    | "summary_report.txt"
-- row_count          | int    | 50
-- processing_time    | float  | 0.015060901641845703
```

## Comparison with Direct File Storage

### Current Approach (File Paths)
✅ Simple - just store paths as text
✅ Flexible - files can be any size
✅ Fast - no need to serialize/deserialize large files
❌ Files are in temp directories (need manual copying)

### Alternative: Store Files in Database
```python
# If you wanted to store file CONTENTS in database:
with open("output.csv") as f:
    file_contents = f.read()

sim2l.save_outputs(
    output_file="output.csv",
    output_file_content=file_contents  # Store contents
)
```

For this example, we use file paths because:
- More efficient for large files
- Follows Unix philosophy (one tool, one job)
- Files can be processed by other tools immediately

## Advanced Usage

### Processing Multiple Files

```python
%%sim2l_inputs
input_files:
  type: Text
  description: "Comma-separated list of file paths"
```

```python
# In notebook
file_paths = [p.strip() for p in input_files.split(',')]
for path in file_paths:
    df = pd.read_csv(path)
    # ... process
```

### Returning File Lists

```python
sim2l.save_outputs(
    output_files=",".join(output_file_list),  # Comma-separated
    file_count=len(output_file_list)
)
```

### Binary Files (Images, etc.)

For binary files, you might want to use base64 encoding:

```python
import base64

# Save image
with open("plot.png", "rb") as f:
    img_data = base64.b64encode(f.read()).decode()

sim2l.save_outputs(
    plot_file="plot.png",
    plot_data=img_data  # Base64 encoded
)
```

## Summary

This example demonstrates the complete workflow for file-based simulations:

1. ✅ File paths as Text inputs (use absolute paths!)
2. ✅ File paths as Text outputs
3. ✅ Multiple processing modes with choice parameters
4. ✅ Database storage of file paths
5. ✅ SQUID IDs for caching
6. ✅ Complete execution tracking

The key insight: **sim2l stores metadata (file paths), not file contents**. This keeps the database lightweight and allows simulations to work with files of any size.
