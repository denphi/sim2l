# Dependency Changes in Sim2l

## Overview

Sim2l has moved from notebook-based result storage (using `nteract-scrapbook`) to SQLite-based run databases. This change improves performance, portability, and enables powerful database services.

## Key Changes

### Removed from Core Dependencies

- **nteract-scrapbook** - Previously required, now optional for notebook simulations

### Added to Core Dependencies

- **flask>=2.0** - For REST API services
- **requests>=2.25** - For service clients
- **psycopg2-binary>=2.9** - For PostgreSQL backend support

## Installation

### Minimal Installation (Run Databases Only)

```bash
pip install sim2l
```

Includes:
- Run database support (SQLite)
- Core simulation functionality
- Basic file management

### With Notebook Support

If you still use notebook-based simulations:

```bash
pip install sim2l[notebooks]
```

Adds:
- scrapbook>=0.5

### With Development Tools

```bash
pip install sim2l[dev]
```

### With All Features

```bash
pip install sim2l[notebooks,dev,docs]
```

## Architecture Changes

### Before (Legacy)

```
Simulation → Notebook Execution → Scrapbook → Notebook File
```

Results stored in:
- Notebook files (`.ipynb`)
- Scrapbook scraps embedded in notebooks
- Separate file cache (PostgreSQL)

### After (Sim2l)

```
Simulation → Execution → Run Database → SQLite File
```

Results stored in:
- Run databases (`.db` files)
- One database per execution
- Complete isolation and portability

Optional:
```
Run Database → Services (Cache/Catalog/Results)
```

## What This Means

### ✅ Benefits

1. **No Scrapbook Dependency** - Core sim2l works without notebooks
2. **Better Performance** - SQLite is faster than notebook parsing
3. **Smaller Files** - Databases are more compact than notebooks
4. **Portability** - Single `.db` file contains everything
5. **Queryable** - SQL queries on run data
6. **Services** - Cache, catalog, and results services

### 🔄 For Notebook Users

If you use notebook-based simulations, you'll need to:

```bash
pip install sim2l[notebooks]
```

This ensures scrapbook is installed for notebook output extraction.

### 📦 For Package Maintainers

Update your dependencies:

**Old**:
```python
install_requires=[
    "sim2l>=1.0",
    "scrapbook>=0.5",  # Was required
]
```

**New**:
```python
install_requires=[
    "sim2l>=2.0",  # Core only
]

# Or with notebooks
install_requires=[
    "sim2l[notebooks]>=2.0",
]
```

## Backward Compatibility

### Notebook Simulations Still Work

Sim2l still supports notebook-based simulations through papermill:

```python
import sim2l

# Notebook-based simulation (requires scrapbook)
sim = sim2l.load("notebook_sim")
result = sim.run(param=100)
```

Just install with `[notebooks]` extra.

### Legacy Code

If you have code that directly uses scrapbook:

```python
# Old code
import scrapbook as sb
data = sb.read_notebook("output.ipynb")
```

You'll need to either:
1. Install `pip install scrapbook` separately, or
2. Migrate to use run databases:

```python
# New code
from sim2l.database import RunDatabase

run_db = RunDatabase(execution_id)
outputs = run_db.get_outputs()
```

## Migration Guide

### Step 1: Update Installation

```bash
# Uninstall old version
pip uninstall sim2l

# Install new version
pip install sim2l  # or sim2l[notebooks] if needed
```

### Step 2: Update Code

**Before**:
```python
import sim2l

sim = sim2l.load("my_sim")
result = sim.run(temp=350)

# Access results from notebook
import scrapbook as sb
nb = sb.read_notebook(result.notebook_path)
output_value = nb.scraps['output_param'].data
```

**After**:
```python
import sim2l
from sim2l.database import RunDatabase

# Configure to use run databases
sim2l.configure(use_run_database=True)

sim = sim2l.load("my_sim")
result = sim.run(temp=350)

# Access results from run database
run_db = RunDatabase(result.execution_id)
outputs = run_db.get_outputs()
output_value = next(o['value'] for o in outputs if o['name'] == 'output_param')
```

### Step 3: Enable Services (Optional)

```python
from sim2l import configure
from sim2l.database import get_session_manager

session = get_session_manager().create_anonymous_session()

configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    cache_session_id=session.session_id
)
```

## Checking Your Dependencies

### See What's Installed

```bash
pip show sim2l
```

Look for:
- **Requires**: Shows core dependencies
- **Required-by**: Shows packages depending on sim2l

### Verify Services Work

```bash
# Start services
./start_services.sh

# Test
python3 test_services.py
```

## FAQ

### Q: Do I need scrapbook anymore?

**A:** Only if you're using notebook-based simulations. For most users, no.

### Q: Will my old code break?

**A:** Not if you install `sim2l[notebooks]`. The notebook execution path still works.

### Q: What if I don't use notebooks?

**A:** Perfect! Just `pip install sim2l` and you're good to go.

### Q: Can I use both notebooks and run databases?

**A:** Yes! Install `sim2l[notebooks]` and enable run databases:

```python
sim2l.configure(use_run_database=True)
```

You'll get both notebook files AND run databases.

### Q: How do I migrate existing results?

**A:** Historical notebook results stay as-is. New runs create run databases. Or use the results service to index historical runs:

```python
from sim2l.database import ResultsClient, get_session_manager

session = get_session_manager().create_anonymous_session()
client = ResultsClient("http://localhost:8003", session_id=session.session_id)

# Register historical runs
for execution_id in historical_runs:
    client.register_result(execution_id)
```

## Summary

- ✅ **scrapbook** moved to optional dependency
- ✅ **flask**, **requests**, **psycopg2-binary** added for services
- ✅ Core sim2l works without notebooks
- ✅ Notebook simulations still supported with `[notebooks]` extra
- ✅ Run databases replace notebook result storage
- ✅ Better performance and portability

For questions or issues, see the documentation or GitHub issues.
