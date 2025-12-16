# Sim2l Database Services - Quick Start Guide

## Overview

Sim2l now includes three integrated database systems:

1. **Per-Run Databases** (SQLite) - One database per execution run
2. **Cache Service** (SQLite/PostgreSQL) - Distributed caching
3. **Catalog Service** (PostgreSQL/SQLite) - Central tool registry

## 5-Minute Setup

### 1. Local Development (No Services)

```python
from sim2l import configure

# Enable per-run databases only
configure(use_run_database=True)

# Your existing code works unchanged
sim = load_simulation("my_sim", version="1.0.0")
result = sim.run(param1=100, param2=200)

# Now you also have a complete run database
from sim2l.database import RunDatabase
run_db = RunDatabase(result.execution_id)
print(run_db.get_summary())
```

**What you get:**
- Complete run isolation in `~/.sim2l/runs/{execution_id}.db`
- All inputs, outputs, logs, and files in one SQLite file
- Portable - copy the file to share the complete run

### 2. Team Environment (Shared Cache)

**Terminal 1 - Start cache service:**
```bash
python -m sim2l.services.cache_service --port 8001
```

**Terminal 2 - Your code:**
```python
from sim2l import configure
from sim2l.database import get_session_manager

# Create session
session = get_session_manager().create_anonymous_session()

# Configure to use cache service
configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    cache_session_id=session.session_id
)

# Cache is automatically checked before execution
result = sim.run(param1=100)  # Might be a cache hit!
```

**What you get:**
- Automatic cache deduplication across your team
- Fast cache lookups without scanning local database
- Cache statistics and analytics

### 3. Full Stack (Enterprise)

**Terminal 1 - Cache service:**
```bash
python -m sim2l.services.cache_service \
  --backend postgresql \
  --db-url postgresql://user:pass@localhost/sim2l_cache \
  --port 8001
```

**Terminal 2 - Catalog service:**
```bash
python -m sim2l.services.catalog_service \
  --backend postgresql \
  --db-url postgresql://user:pass@localhost/sim2l_catalog \
  --port 8002
```

**Terminal 3 - Your code:**
```python
from sim2l import configure
from sim2l.database import get_session_manager

# Authenticate
manager = get_session_manager()
manager.create_user("alice", "secret", role="developer")
session = manager.authenticate("alice", "secret")

# Configure services
configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    cache_session_id=session.session_id,
    catalog_service_url="http://localhost:8002",
    catalog_session_id=session.session_id,
    catalog_auto_sync=True
)

# Everything else is automatic!
result = sim.run(param1=100)
```

**What you get:**
- Distributed caching
- Central tool registry
- Automatic sync of new tools
- Execution statistics
- Access control

## Common Operations

### Query a Run Database

```python
from sim2l.database import RunDatabase

run_db = RunDatabase("execution-id-here")

# Get summary
summary = run_db.get_summary()
print(f"Status: {summary['status']}")
print(f"Duration: {summary['duration_seconds']}s")
print(f"Errors: {summary['error_count']}")

# Get all outputs
outputs = run_db.get_outputs()
for name, data in outputs.items():
    print(f"{name}: {data['value']} {data['units']}")

# Get error logs
errors = run_db.get_errors()
for error in errors:
    print(f"{error['timestamp']}: {error['message']}")

# Get all logs
logs = run_db.get_logs(level="INFO", limit=100)
```

### Manual Cache Operations

```python
from sim2l.database import CacheClient

cache = CacheClient("http://localhost:8001", session_id="...")

# Check cache
result = cache.get("cache-key-here")
if result:
    print(f"Found execution: {result['execution_id']}")

# Invalidate cache for a simulation
count = cache.invalidate(
    simulation_name="my_sim",
    reason="Bug fix in v2.0"
)
print(f"Invalidated {count} entries")

# Get statistics
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate_percent']}%")
```

### Search Catalog

```python
from sim2l.database import CatalogClient

catalog = CatalogClient("http://localhost:8002", session_id="...")

# Search for simulations
results = catalog.search(
    query="thermal",
    tags=["physics"],
    status="active"
)

for sim in results:
    print(f"{sim['name']} v{sim['version']}")
    print(f"  Author: {sim['author']}")
    print(f"  Executions: {sim['total_executions']}")
    print(f"  Cache hit rate: {sim['cache_hit_rate']}%")

# Get specific simulation
sim = catalog.get_simulation("thermal_analysis", version="1.0.0")
print(f"Input schema: {sim['input_schema']}")
print(f"Dependencies: {sim['dependencies']}")

# Sync local simulations to catalog
results = catalog.sync_local_simulations()
print(f"Synced {results['sync_requested']} new simulations")
```

### Session Management

```python
from sim2l.database import SessionManager

manager = SessionManager()

# Create users
admin_id = manager.create_user("admin", "admin", role="admin")
dev_id = manager.create_user("alice", "secret", role="developer")
user_id = manager.create_user("bob", "password", role="user")

# Authenticate
session = manager.authenticate("alice", "secret")
print(f"Session ID: {session.session_id}")
print(f"Privileges: {session.privileges}")
print(f"Expires: {session.expires_at}")

# Check privilege
if manager.check_privilege(session.session_id, "catalog_update"):
    print("Can register new simulations")

# List active sessions
for s in manager.list_sessions():
    print(f"{s['username']}: expires {s['expires_at']}")
```

## Configuration Options

### Environment Variables

```bash
# Run database
export SIM2L_USE_RUN_DATABASE=true
export SIM2L_RUN_DB_BASE_PATH=$HOME/.sim2l/runs

# Cache service
export SIM2L_CACHE_SERVICE_URL=http://localhost:8001
export SIM2L_CACHE_SESSION_ID=your-session-id

# Catalog service
export SIM2L_CATALOG_SERVICE_URL=http://localhost:8002
export SIM2L_CATALOG_SESSION_ID=your-session-id
export SIM2L_CATALOG_AUTO_SYNC=true
```

### Config File (~/.sim2l/config.json)

```json
{
  "use_run_database": true,
  "run_db_base_path": "~/.sim2l/runs",
  "cache_service_url": "http://localhost:8001",
  "catalog_service_url": "http://localhost:8002",
  "catalog_auto_sync": true
}
```

### Programmatic

```python
from sim2l import configure

configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    catalog_service_url="http://localhost:8002"
)
```

## Service Commands

### Cache Service

```bash
# SQLite (development)
python -m sim2l.services.cache_service \
  --backend sqlite \
  --db-path ~/.sim2l/cache.db \
  --port 8001

# PostgreSQL (production)
python -m sim2l.services.cache_service \
  --backend postgresql \
  --db-url postgresql://user:password@localhost/sim2l_cache \
  --host 0.0.0.0 \
  --port 8001
```

### Catalog Service

```bash
# SQLite (development)
python -m sim2l.services.catalog_service \
  --backend sqlite \
  --db-path ~/.sim2l/catalog.db \
  --port 8002

# PostgreSQL (production)
python -m sim2l.services.catalog_service \
  --backend postgresql \
  --db-url postgresql://user:password@localhost/sim2l_catalog \
  --host 0.0.0.0 \
  --port 8002
```

## Database Backends

### When to use SQLite

- Local development
- Single user
- Testing
- Per-run databases (always SQLite)

### When to use PostgreSQL

- Production environments
- Multiple users
- High concurrency
- Cache service (recommended)
- Catalog service (recommended)

## Health Checks

```bash
# Cache service
curl http://localhost:8001/health

# Catalog service
curl http://localhost:8002/health
```

## Example Workflows

### Workflow 1: Debug a Failed Run

```python
from sim2l.database import RunDatabase

# Find the execution ID from the error message
run_db = RunDatabase("failed-execution-id")

# Check what went wrong
summary = run_db.get_summary()
print(f"Status: {summary['status']}")
print(f"Error: {summary['error_message']}")

# Get detailed error logs
errors = run_db.get_errors()
for error in errors:
    print(f"\n{error['timestamp']}")
    print(f"Logger: {error['logger']}")
    print(f"Message: {error['message']}")
    if error['stack_trace']:
        print(f"Stack trace:\n{error['stack_trace']}")

# Check inputs (maybe wrong parameter?)
inputs = run_db.get_inputs()
print(f"\nInputs used: {inputs}")

# Check cell executions (for notebook runs)
# ... identify which cell failed
```

### Workflow 2: Share Results with Colleague

```bash
# Run database is a single file
cd ~/.sim2l/runs
ls -lh abc-123-execution-id.db

# Email or share this file
# Colleague can query it:
```

```python
from sim2l.database import RunDatabase

run_db = RunDatabase.from_file("received-run.db")
outputs = run_db.get_outputs()
artifacts = run_db.get_artifacts()
# ... full access to all run data
```

### Workflow 3: Performance Analysis

```python
from sim2l.database import RunDatabase
import sqlite3

# Query multiple runs
runs_dir = Path.home() / ".sim2l" / "runs"
durations = []

for db_file in runs_dir.glob("*.db"):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT duration_seconds, simulation_name FROM run_metadata"
    )
    row = cursor.fetchone()
    if row:
        durations.append({
            'duration': row[0],
            'simulation': row[1],
            'db': db_file.name
        })
    conn.close()

# Find slowest runs
slowest = sorted(durations, key=lambda x: x['duration'], reverse=True)[:10]
for run in slowest:
    print(f"{run['simulation']}: {run['duration']:.2f}s - {run['db']}")
```

### Workflow 4: Team Cache Management

```python
from sim2l.database import CacheClient

cache = CacheClient("http://team-cache:8001", session_id="...")

# Check what's cached for your simulation
stats = cache.get_stats(simulation_id=42)
print(f"This simulation has {stats['total_entries']} cached results")
print(f"Hit rate: {stats['hit_rate_percent']}%")

# New version released? Invalidate old cache
count = cache.invalidate(
    simulation_name="my_sim",
    simulation_version="1.0.0",  # Old version
    reason="Upgrading to v2.0.0"
)
print(f"Invalidated {count} cache entries for v1.0.0")
```

## Troubleshooting

### "Session expired" error

```python
# Re-authenticate and update clients
session = manager.authenticate("username", "password")

cache.session_id = session.session_id
catalog.session_id = session.session_id
```

### Cache service not responding

```bash
# Check if service is running
curl http://localhost:8001/health

# Check logs (if you redirected them)
tail -f cache_service.log

# Restart service
python -m sim2l.services.cache_service --port 8001
```

### Run database missing

```python
# Check if run databases are enabled
from sim2l import get_config
config = get_config()
print(f"Run DB enabled: {config.use_run_database}")

# Enable if needed
configure(use_run_database=True)
```

## Next Steps

1. Read full documentation: [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md)
2. Explore the schemas:
   - [run_db_schema.sql](sim2l/database/run_db_schema.sql)
   - [cache_service_schema.sql](sim2l/database/cache_service_schema.sql)
   - [master_catalog_schema.sql](sim2l/database/master_catalog_schema.sql)
3. Check out examples in `tests/database/`
4. Set up PostgreSQL for production use

## Questions?

- Documentation: Full architecture in DATABASE_ARCHITECTURE.md
- Examples: See `tests/database/test_*.py`
- Issues: GitHub issue tracker
