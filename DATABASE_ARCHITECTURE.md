# Sim2l Database Architecture

## Overview

The sim2l migration includes three integrated database systems designed for scalability, distributed caching, and centralized tool management:

1. **Per-Run SQLite Databases** - Complete isolation for each execution
2. **Remote Cache Service** - Distributed caching with session-based access control
3. **Master Catalog** - Central registry for all sim2l tools and versions

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Sim2l Client                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Executor     │  │ Cache Client │  │ Catalog      │     │
│  │              │  │              │  │ Client       │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Run Database    │  │  Cache Service   │  │ Catalog Service  │
│ (SQLite)        │  │  (REST API)      │  │  (REST API)      │
│                 │  │                  │  │                  │
│ Per-execution   │  │  Session Auth    │  │  Session Auth    │
│ isolation       │  │  Cache Lookup    │  │  Tool Registry   │
│                 │  │  Statistics      │  │  Auto-sync       │
│ - Inputs        │  │                  │  │  Statistics      │
│ - Outputs       │  │  Backend:        │  │                  │
│ - Files         │  │  - SQLite        │  │  Backend:        │
│ - Logs          │  │  - PostgreSQL    │  │  - PostgreSQL    │
│ - Metrics       │  │                  │  │  - SQLite        │
└─────────────────┘  └──────────────────┘  └──────────────────┘
```

## 1. Per-Run SQLite Database

### Purpose
Each execution run creates its own SQLite database, providing:
- Complete run isolation
- Full provenance tracking
- Portability (single file contains all run data)
- Efficient storage for logs, metrics, and artifacts

### Schema

**Tables:**
- `run_metadata` - Execution metadata (ID, status, timing, executor info)
- `inputs` - Input parameters with types and units
- `outputs` - Output results with types and units
- `artifacts` - Files and binary data (plots, notebooks, etc.)
- `logs` - Structured logs with levels and context
- `cell_executions` - Notebook cell-level tracking
- `metrics` - Performance and custom metrics
- `resource_usage` - CPU, memory, disk, network usage
- `provenance` - Data lineage tracking
- `tags` - Run categorization
- `checkpoints` - State snapshots for long-running sims

### Usage

```python
from sim2l.database import RunDatabase

# Create run database
run_db = RunDatabase(execution_id="abc-123")

# Initialize run
run_db.initialize_run(
    simulation_name="thermal_analysis",
    simulation_version="1.0.0",
    squid_id="thermal/1.0.0/xyz789",
    executor_type="notebook",
    user_id="user@example.com",
    session_id="session-456"
)

# Save inputs
run_db.save_input("temperature", 350.0, "Number", units="kelvin")

# Save outputs
run_db.save_output("max_temp", 425.0, "Number", units="kelvin")

# Log execution
run_db.log("INFO", "Starting thermal simulation")

# Save artifacts
with open("plot.png", "rb") as f:
    run_db.save_artifact(
        name="temperature_plot.png",
        content=f.read(),
        category="plot",
        content_type="image/png"
    )

# Complete run
run_db.complete_run(status="completed", duration_seconds=12.5)

# Query results
summary = run_db.get_summary()
outputs = run_db.get_outputs()
errors = run_db.get_errors()
```

### Location
- Default: `~/.sim2l/runs/{execution_id}.db`
- Configurable via `Config.run_db_base_path`
- Environment variable: `SIM2L_RUN_DB_BASE_PATH`

### Advantages
- **Portability**: Copy single file to share complete run
- **Debugging**: All logs and artifacts in one place
- **Archival**: Easy to archive or delete old runs
- **Query**: SQL queries for analysis

## 2. Remote Cache Service

### Purpose
Centralized distributed cache for:
- Deduplication across multiple users
- Fast cache lookups without local repository scans
- Session-based access control
- Cache statistics and analytics

### API Endpoints

#### GET /cache/{cache_key}
Retrieve cached result.

**Headers:**
- `X-Session-ID`: Session ID for authentication

**Response:**
```json
{
  "execution_id": "abc-123",
  "squid_id": "thermal/1.0.0/xyz789",
  "run_db_path": "/path/to/run/abc-123.db",
  "metadata": {}
}
```

#### POST /cache
Store cache entry.

**Headers:**
- `X-Session-ID`: Session ID for authentication

**Body:**
```json
{
  "cache_key": "hash123",
  "simulation_id": 42,
  "simulation_name": "thermal_analysis",
  "simulation_version": "1.0.0",
  "execution_id": "abc-123",
  "squid_id": "thermal/1.0.0/xyz789",
  "input_hash": "hash456",
  "run_db_path": "/path/to/run/abc-123.db",
  "ttl_seconds": 86400,
  "metadata": {}
}
```

#### POST /cache/invalidate
Invalidate cache entries.

**Body:**
```json
{
  "simulation_id": 42,
  "simulation_name": "thermal_analysis",
  "simulation_version": "1.0.0",
  "pattern": "thermal%",
  "reason": "Bug fix in version 1.0.1"
}
```

#### GET /cache/stats
Get cache statistics.

**Query Parameters:**
- `simulation_id` (optional): Filter by simulation

**Response:**
```json
{
  "total_requests": 1000,
  "cache_hits": 750,
  "cache_misses": 250,
  "hit_rate_percent": 75.0,
  "total_entries": 500
}
```

### Running the Service

#### SQLite Backend (Default)
```bash
python -m sim2l.services.cache_service \
  --backend sqlite \
  --db-path ~/.sim2l/cache.db \
  --host 0.0.0.0 \
  --port 8001
```

#### PostgreSQL Backend
```bash
python -m sim2l.services.cache_service \
  --backend postgresql \
  --db-url postgresql://user:password@localhost/sim2l_cache \
  --host 0.0.0.0 \
  --port 8001
```

### Client Usage

```python
from sim2l.database import CacheClient
from sim2l.database import get_session_manager

# Authenticate
session_manager = get_session_manager()
session = session_manager.authenticate("username", "password")

# Connect to cache service
cache = CacheClient(
    service_url="http://localhost:8001",
    session_id=session.session_id
)

# Check cache
cached_result = cache.get("cache_key_123")
if cached_result:
    print(f"Cache hit! Execution ID: {cached_result['execution_id']}")
else:
    # Run simulation and cache result
    cache.set(
        cache_key="cache_key_123",
        simulation_id=42,
        simulation_name="thermal",
        simulation_version="1.0.0",
        execution_id="abc-123",
        squid_id="thermal/1.0.0/xyz",
        input_hash="hash456",
        run_db_path="/path/to/run.db"
    )

# Invalidate cache
count = cache.invalidate(simulation_id=42, reason="Bug fix")
print(f"Invalidated {count} entries")

# Get statistics
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate_percent']}%")
```

### Local Mode (No Service)

For development or single-user scenarios:

```python
from sim2l.database import LocalCacheClient

# Local in-memory cache
cache = LocalCacheClient()

# Same API as CacheClient
cached_result = cache.get("cache_key")
cache.set(cache_key="cache_key", ...)
```

## 3. Master Catalog Service

### Purpose
Central registry for:
- All sim2l tools and versions
- Schema metadata and documentation
- Execution statistics
- Automatic synchronization from installations
- Access control and privileges

### Database Schema (PostgreSQL)

**Core Tables:**
- `users` - User accounts
- `sessions` - Active sessions with privileges
- `simulations` - Registered sim2l tools
- `execution_stats` - Aggregated statistics
- `execution_registry` - Lightweight execution references
- `installations` - Client installations
- `sync_queue` - Pending sync requests
- `access_control` - Simulation ownership
- `audit_log` - Change tracking

### API Endpoints

#### GET /simulations/search
Search for simulations.

**Query Parameters:**
- `query`: Name pattern
- `tags`: Comma-separated tags
- `status`: active, deprecated, archived, all
- `limit`: Max results

**Response:**
```json
[
  {
    "id": 42,
    "name": "thermal_analysis",
    "version": "1.0.0",
    "description": "Thermal simulation",
    "tags": ["physics", "thermal"],
    "author": "John Doe",
    "status": "active",
    "created_at": "2024-01-01T00:00:00",
    "total_executions": 1000,
    "cache_hit_rate": 75.0
  }
]
```

#### GET /simulations/{name}
Get simulation metadata.

**Query Parameters:**
- `version` (optional): Specific version (default: latest)

#### POST /simulations
Register new simulation (requires privileges).

**Body:**
```json
{
  "name": "thermal_analysis",
  "version": "1.0.0",
  "description": "Thermal simulation",
  "author": "John Doe",
  "tags": ["physics", "thermal"],
  "input_schema": {...},
  "output_schema": {...},
  "workflow_type": "notebook",
  "workflow_hash": "sha256hash",
  "dependencies": ["numpy", "scipy"],
  "auto_approve": false
}
```

#### POST /executions
Record execution in registry.

#### GET /simulations/{id}/stats
Get execution statistics for simulation.

#### POST /sync/auto
Auto-sync local simulations to catalog.

### Running the Service

```bash
# PostgreSQL backend (recommended)
python -m sim2l.services.catalog_service \
  --backend postgresql \
  --db-url postgresql://user:password@localhost/sim2l_catalog \
  --host 0.0.0.0 \
  --port 8002

# SQLite backend (development)
python -m sim2l.services.catalog_service \
  --backend sqlite \
  --db-path ~/.sim2l/catalog.db \
  --host 0.0.0.0 \
  --port 8002
```

### Client Usage

```python
from sim2l.database import CatalogClient, get_session_manager

# Authenticate
session = get_session_manager().authenticate("user", "password")

# Connect to catalog
catalog = CatalogClient(
    service_url="http://localhost:8002",
    session_id=session.session_id
)

# Search simulations
results = catalog.search(query="thermal", tags=["physics"])
for sim in results:
    print(f"{sim['name']} v{sim['version']}: {sim['description']}")

# Get specific simulation
sim = catalog.get_simulation("thermal_analysis", version="1.0.0")
print(f"Input schema: {sim['input_schema']}")

# Register new simulation (requires write privilege)
catalog.register_simulation(
    name="my_simulation",
    version="1.0.0",
    description="My custom simulation",
    author="Me",
    tags=["custom"],
    input_schema={...},
    output_schema={...},
    workflow_type="notebook",
    workflow_hash="abc123"
)

# Auto-sync local simulations
results = catalog.sync_local_simulations()
print(f"Synced {results['sync_requested']} simulations")

# Get statistics
stats = catalog.get_stats(simulation_id=42)
print(f"Total executions: {stats['total_executions']}")
```

### Auto-Sync Mechanism

When a new sim2l tool is installed locally:

1. Client detects simulation not in catalog
2. Submits sync request to `/sync/pending`
3. Admin approves request via `/sync/{id}/approve`
4. Simulation added to catalog

Or with `auto_approve=True` (requires admin privilege):

```python
catalog.register_simulation(..., auto_approve=True)
```

### Local Mode (No Service)

```python
from sim2l.database import LocalCatalogClient

# Use local repository directly
catalog = LocalCatalogClient()

# Same search API, uses local database
results = catalog.search(query="thermal")
```

## 4. Session Management & Authentication

### SessionManager

Handles user authentication and privilege management.

```python
from sim2l.database import SessionManager

manager = SessionManager()

# Create user
user_id = manager.create_user(
    username="alice",
    password="secret",
    role="developer",  # admin, developer, user
    email="alice@example.com"
)

# Authenticate
session = manager.authenticate("alice", "secret")
print(f"Session ID: {session.session_id}")
print(f"Privileges: {session.privileges}")

# Check privileges
has_write = manager.check_privilege(session.session_id, "write")
has_admin = manager.check_privilege(session.session_id, "admin")

# Anonymous session (local development)
anon_session = manager.create_anonymous_session(
    privileges=["read", "write"]
)

# Invalidate session
manager.invalidate_session(session.session_id)
```

### Privilege Levels

- **read**: View simulations and search catalog
- **write**: Execute simulations and cache results
- **catalog_update**: Register new simulations
- **admin**: All privileges + approve sync requests

### Role Mapping

- **user**: read, write
- **developer**: read, write, catalog_update
- **admin**: all privileges

## Configuration

### Environment Variables

```bash
# Run database
export SIM2L_USE_RUN_DATABASE=true
export SIM2L_RUN_DB_BASE_PATH=~/.sim2l/runs

# Cache service
export SIM2L_CACHE_SERVICE_URL=http://localhost:8001
export SIM2L_CACHE_SESSION_ID=session-abc-123

# Catalog service
export SIM2L_CATALOG_SERVICE_URL=http://localhost:8002
export SIM2L_CATALOG_SESSION_ID=session-abc-123
export SIM2L_CATALOG_AUTO_SYNC=true
```

### Configuration File (~/.sim2l/config.json)

```json
{
  "db_path": "~/.sim2l/simulations.db",
  "cache_enabled": true,
  "use_run_database": true,
  "run_db_base_path": "~/.sim2l/runs",
  "cache_service_url": "http://localhost:8001",
  "catalog_service_url": "http://localhost:8002",
  "catalog_auto_sync": true,
  "log_level": "INFO"
}
```

### Programmatic Configuration

```python
from sim2l import configure

configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    catalog_service_url="http://localhost:8002",
    catalog_auto_sync=True
)
```

## Deployment Scenarios

### Scenario 1: Local Development (No Services)

```python
from sim2l.database import LocalCacheClient, LocalCatalogClient

# Use local implementations (no remote services)
cache = LocalCacheClient()
catalog = LocalCatalogClient()

# Everything runs in-memory or against local database
```

**Configuration:**
```json
{
  "use_run_database": true,
  "cache_service_url": null,
  "catalog_service_url": null
}
```

### Scenario 2: Team Environment (Shared Cache)

**Start cache service:**
```bash
python -m sim2l.services.cache_service \
  --backend postgresql \
  --db-url postgresql://user:pass@dbhost/sim2l_cache
```

**Client configuration:**
```json
{
  "use_run_database": true,
  "cache_service_url": "http://cache-server:8001",
  "catalog_service_url": null
}
```

### Scenario 3: Enterprise (Full Stack)

**Infrastructure:**
- PostgreSQL database cluster
- Cache service (replicated)
- Catalog service (replicated)
- Load balancer

**Client configuration:**
```json
{
  "use_run_database": true,
  "cache_service_url": "https://cache.company.com",
  "catalog_service_url": "https://catalog.company.com",
  "catalog_auto_sync": true
}
```

## Database Backends

### SQLite (Default)

**Advantages:**
- No setup required
- Single-file databases
- Perfect for development
- Portable

**Limitations:**
- No concurrent writes
- Single server only
- Limited for high concurrency

**Use Cases:**
- Local development
- Single-user installations
- Per-run databases
- Testing

### PostgreSQL (Production)

**Advantages:**
- High concurrency
- Distributed deployment
- Advanced features (JSONB, full-text search)
- Stored procedures for complex logic

**Limitations:**
- Requires separate database server
- More complex setup

**Use Cases:**
- Cache service (multi-user)
- Catalog service (central registry)
- Production environments
- Team/enterprise deployments

## Integration with Existing Sim2l

The database systems integrate seamlessly with existing sim2l execution:

```python
from sim2l import deploy_simulation, load_simulation
from sim2l.database import RunDatabase, CacheClient, CatalogClient

# Deploy simulation
sim_id = deploy_simulation(
    notebook="thermal.ipynb",
    name="thermal_analysis",
    version="1.0.0"
)

# Load and execute
sim = load_simulation("thermal_analysis", version="1.0.0")

# With run database enabled, execution automatically:
# 1. Creates per-run SQLite database
# 2. Checks remote cache (if configured)
# 3. Logs all inputs, outputs, artifacts
# 4. Records execution in catalog (if configured)
# 5. Updates cache with results

result = sim.run(temperature=350, power=25)

# Access run database
run_db = RunDatabase(result.execution_id)
summary = run_db.get_summary()
logs = run_db.get_logs(level="ERROR")
```

## Security Considerations

1. **Session Management**: All remote services require valid session IDs
2. **Privilege Checks**: Operations validated against user privileges
3. **Audit Logging**: All catalog changes logged with user/timestamp
4. **HTTPS**: Use HTTPS in production for encrypted transport
5. **Database Security**: PostgreSQL user permissions and SSL connections
6. **Input Validation**: All API inputs validated and sanitized

## Monitoring & Maintenance

### Cache Service

**Health check:**
```bash
curl http://localhost:8001/health
```

**Statistics:**
```bash
curl http://localhost:8001/cache/stats
```

**Cleanup:**
```sql
-- Remove expired entries
SELECT evict_expired_entries();

-- Remove old access logs
SELECT cleanup_old_logs(90);  -- Keep 90 days
```

### Catalog Service

**Pending sync requests:**
```sql
SELECT * FROM pending_sync_requests;
```

**Execution statistics:**
```sql
SELECT * FROM execution_stats
WHERE period_start >= CURRENT_DATE - INTERVAL '30 days';
```

**Audit trail:**
```sql
SELECT * FROM audit_log
WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY timestamp DESC;
```

## Future Enhancements

1. **Redis Backend**: Ultra-fast cache using Redis
2. **S3 Artifact Storage**: Store large artifacts in S3
3. **GraphQL API**: Alternative API for complex queries
4. **Web UI**: Browser-based catalog explorer
5. **Metrics Dashboard**: Real-time statistics and monitoring
6. **Distributed Execution**: Submit jobs to compute clusters
7. **Workflow DAGs**: Complex multi-step workflows
8. **Data Lineage**: Track data dependencies across simulations

## Troubleshooting

### Cache service not responding

```bash
# Check service status
curl http://localhost:8001/health

# Check logs
tail -f ~/.sim2l/logs/cache_service.log

# Restart service
python -m sim2l.services.cache_service --port 8001
```

### Session expired

```python
# Re-authenticate
from sim2l.database import get_session_manager

session = get_session_manager().authenticate("user", "password")

# Update client
cache.session_id = session.session_id
catalog.session_id = session.session_id
```

### Sync request stuck

```python
# Check pending requests
pending = catalog.get_pending_sync_requests()

# Approve request (requires admin)
catalog.approve_sync_request(request_id=123)
```

### Run database corruption

```bash
# Verify database
sqlite3 ~/.sim2l/runs/abc-123.db "PRAGMA integrity_check;"

# Export data
sqlite3 ~/.sim2l/runs/abc-123.db ".dump" > backup.sql

# Rebuild database
sqlite3 new.db < backup.sql
```

## Testing

See `/Users/denphi/Documents/Github/sim2l/tests/database/` for comprehensive test suite covering:

- Run database operations
- Cache service API
- Catalog service API
- Session management
- Integration tests
- Performance tests

Run tests:
```bash
pytest tests/database/ -v
```

## License

Same license as sim2l project.

## Support

For issues and questions:
- GitHub Issues: [sim2l repository]
- Documentation: [sim2l docs]
- Email: [maintainer email]
