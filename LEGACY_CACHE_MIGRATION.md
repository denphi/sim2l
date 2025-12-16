

# Legacy Cache Migration Guide

## Overview

The `papers` implementation used a PostgreSQL-based cache system with a simple schema:
- **Database**: `simtool_cache`
- **Tables**: `simtool_cache_files`, `simtool_cache_users`, etc.
- **Schema**: `ID` (VARCHAR), `VALUES` (JSON)
- **Access**: Direct PostgreSQL via `PsqlModel` base class

The new `sim2l` implementation provides:
- Per-run SQLite databases
- Distributed cache service with REST API
- Master catalog registry

This guide explains how to maintain backward compatibility while migrating to the new system.

---

## Architecture Comparison

### Old System (papers/)

```
┌─────────────────────────────────────┐
│   Application Code                  │
│   (File, User, Folder models)       │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│   PsqlModel Base Class              │
│   - select(id)                      │
│   - insert(id, values)              │
│   - update(id, values)              │
│   - delete(id)                      │
│   - filter(predicate)               │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│   PostgreSQL Database               │
│   Database: simtool_cache           │
│   Tables: simtool_cache_*           │
│   Schema: ID, VALUES (JSON)         │
└─────────────────────────────────────┘
```

### New System (sim2l/)

```
┌─────────────────────────────────────┐
│   Application Code                  │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│   Legacy Adapter (PsqlModelAdapter) │
│   - Translates old API to new       │
│   - Maintains compatibility         │
└────────┬───────────┬────────────────┘
         │           │
         ▼           ▼
    ┌────────┐   ┌──────────────────┐
    │ Legacy │   │ New Cache System │
    │  PG DB │   │ - Cache Service  │
    │        │   │ - Run Databases  │
    └────────┘   │ - Catalog        │
                 └──────────────────┘
```

---

## Migration Strategies

### Strategy 1: Direct Cutover (Recommended for New Projects)

**When**: Starting fresh or can afford downtime

**Steps**:
1. Disable legacy backend
2. Use new cache system exclusively
3. No migration of old data needed

**Configuration**:
```python
# In environment or config
USE_LEGACY_CACHE_BACKEND=false
ENABLE_DUAL_WRITE_CACHE=false

# Use new cache
from sim2l import configure
configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001"
)
```

**Pros**:
- Clean start
- No legacy baggage
- Full new features

**Cons**:
- Loses old cache data
- Requires code updates

---

### Strategy 2: Dual-Write Migration (Zero Downtime)

**When**: Need to maintain old system while transitioning

**Steps**:
1. Enable dual-write mode
2. All writes go to both old and new systems
3. Reads come from old system initially
4. Gradually switch reads to new system
5. Eventually disable old system

**Configuration**:
```python
# Phase 1: Dual write, read from old
USE_LEGACY_CACHE_BACKEND=true
ENABLE_DUAL_WRITE_CACHE=true

# Phase 2: Read from new, still dual write
USE_LEGACY_CACHE_BACKEND=false
ENABLE_DUAL_WRITE_CACHE=true

# Phase 3: New only
USE_LEGACY_CACHE_BACKEND=false
ENABLE_DUAL_WRITE_CACHE=false
```

**Pros**:
- Zero downtime
- Gradual migration
- Rollback capability

**Cons**:
- Double storage cost temporarily
- More complex setup

---

### Strategy 3: Read-Through Cache (Gradual Migration)

**When**: Large existing cache that's expensive to recreate

**Steps**:
1. Configure legacy as read-only
2. Cache misses in new system fall back to legacy
3. Gradually populate new system
4. Eventually remove legacy

**Implementation**:
```python
from sim2l.database.legacy_cache_adapter import PsqlModelAdapter

class MyModel(PsqlModelAdapter):
    _table = 'my_legacy_table'

    @classmethod
    def select(cls, id):
        # Try new system first
        result = cls._select_new(id)
        if result is None:
            # Fall back to legacy
            result = cls._select_legacy(id)
            if result:
                # Populate new system
                cls._update_new(id, result)
        return result
```

**Pros**:
- Preserve existing cache
- Gradual data migration
- Performance improvement over time

**Cons**:
- Requires custom code
- Temporary complexity

---

## Code Migration Examples

### Old Code (papers/)

```python
from api.models.file import File

# Create file
file = File.create(
    name='output.dat',
    size=1024,
    uri='/path/to/file',
    creator='user123'
)

# Find by ID
file = File.find('file-abc-123')

# Update
File.update('file-abc-123', {'size': 2048})

# Filter
files = File.filter({'parent_id': 'folder-xyz'})

# Delete
File.delete('file-abc-123')
```

### New Code (sim2l/) - Option 1: Using Adapter

```python
from sim2l.database.legacy_cache_adapter import LegacyFileModel as File

# Same API as before!
file = File.create(
    name='output.dat',
    size=1024,
    uri='/path/to/file',
    creator='user123'
)

# Configure backend via environment
# USE_LEGACY_CACHE_BACKEND=true  (use old PostgreSQL)
# USE_LEGACY_CACHE_BACKEND=false (use new cache service)
```

### New Code (sim2l/) - Option 2: Native New System

```python
from sim2l.database import CacheClient, RunDatabase

# Use run database for file metadata
run_db = RunDatabase(execution_id)
run_db.save_artifact(
    name='output.dat',
    content=file_content,
    category='output',
    content_type='application/octet-stream'
)

# Use cache for execution results
cache = CacheClient("http://localhost:8001", session_id=session.session_id)
cache.set(
    cache_key="file-abc-123",
    simulation_id=42,
    simulation_name="my_simulation",
    simulation_version="1.0.0",
    execution_id=execution_id,
    squid_id="my_sim/1.0.0/xyz",
    input_hash="hash123",
    run_db_path=run_db.db_path
)
```

---

## Environment Variables

### Legacy Backend Configuration

```bash
# PostgreSQL connection (legacy)
export LEGACY_CACHE_HOST="squiddb.nanohub.org"
export LEGACY_CACHE_PORT="5432"
export LEGACY_CACHE_USER_R="hub"
export LEGACY_CACHE_PWD_R="password"
export LEGACY_CACHE_USER_W="hub_write"
export LEGACY_CACHE_PWD_W="password"

# Migration mode
export USE_LEGACY_CACHE_BACKEND=true  # true = use old PostgreSQL
export ENABLE_DUAL_WRITE_CACHE=false  # true = write to both systems
```

### New System Configuration

```bash
# New cache service
export SIM2L_CACHE_SERVICE_URL=http://localhost:8001
export SIM2L_CACHE_SESSION_ID=session-id-here

# Per-run databases
export SIM2L_USE_RUN_DATABASE=true
export SIM2L_RUN_DB_BASE_PATH=$HOME/.sim2l/runs

# Catalog
export SIM2L_CATALOG_SERVICE_URL=http://localhost:8002
export SIM2L_CATALOG_SESSION_ID=session-id-here
```

---

## Data Migration Script

For bulk migration of existing cache data:

```python
#!/usr/bin/env python
"""
Migrate data from legacy PostgreSQL cache to new cache system.
"""

import os
os.environ['USE_LEGACY_CACHE_BACKEND'] = 'true'

from sim2l.database.legacy_cache_adapter import LegacyFileModel
from sim2l.database import CacheClient, get_session_manager

# Authenticate
manager = get_session_manager()
session = manager.create_anonymous_session(privileges=['admin'])

# Connect to new cache
cache = CacheClient("http://localhost:8001", session_id=session.session_id)

# Get all legacy entries
# Note: This requires a custom method to list all IDs
legacy_ids = get_all_legacy_ids()  # Custom function

migrated = 0
errors = 0

for legacy_id in legacy_ids:
    try:
        # Get from legacy
        data = LegacyFileModel.select(legacy_id)

        if data:
            # Write to new system
            cache.set(
                cache_key=f"simtool_cache_files:{legacy_id}",
                simulation_id=0,
                simulation_name="legacy",
                simulation_version="1.0.0",
                execution_id=f"legacy-{legacy_id}",
                squid_id=f"legacy/files/{legacy_id}",
                input_hash=legacy_id,
                run_db_path="",
                metadata={"legacy_values": data, "legacy_table": "simtool_cache_files"}
            )
            migrated += 1

            if migrated % 100 == 0:
                print(f"Migrated {migrated} entries...")

    except Exception as e:
        print(f"Error migrating {legacy_id}: {e}")
        errors += 1

print(f"Migration complete: {migrated} migrated, {errors} errors")
```

---

## Testing Compatibility

### Unit Tests

```python
import os
import pytest

# Test with legacy backend
os.environ['USE_LEGACY_CACHE_BACKEND'] = 'true'
from sim2l.database.legacy_cache_adapter import LegacyFileModel

def test_legacy_backend():
    """Test that legacy backend works."""
    file = LegacyFileModel.create(name='test.dat', size=100)
    assert file is not None

    found = LegacyFileModel.find(file['id'])
    assert found['name'] == 'test.dat'

    LegacyFileModel.delete(file['id'])


# Test with new backend
os.environ['USE_LEGACY_CACHE_BACKEND'] = 'false'
from sim2l.database.legacy_cache_adapter import LegacyFileModel

def test_new_backend():
    """Test that new backend works with legacy API."""
    file = LegacyFileModel.create(name='test.dat', size=100)
    assert file is not None

    found = LegacyFileModel.find(file['id'])
    assert found['name'] == 'test.dat'
```

---

## Performance Considerations

### Legacy PostgreSQL
- **Latency**: Network latency to remote database
- **Throughput**: Limited by PostgreSQL connection pool
- **Scalability**: Single database bottleneck

### New Cache System
- **Latency**: <10ms for local cache, <50ms for remote
- **Throughput**: 10,000+ req/sec with PostgreSQL backend
- **Scalability**: Horizontal scaling with multiple cache instances

### Recommendations

1. **For read-heavy workloads**: New cache service provides better performance
2. **For write-heavy workloads**: Consider batch writes to reduce overhead
3. **For distributed systems**: New cache service with PostgreSQL backend
4. **For single-server**: Local cache (in-memory) is fastest

---

## Troubleshooting

### Issue: Cannot connect to legacy database

```python
# Check configuration
from sim2l.database.legacy_cache_adapter import LegacyCacheConfig

print(f"Host: {LegacyCacheConfig.HOST}")
print(f"Port: {LegacyCacheConfig.PORT}")
print(f"Database: {LegacyCacheConfig.DATABASE_NAME}")

# Test connection
import psycopg2
try:
    conn = psycopg2.connect(
        host=LegacyCacheConfig.HOST,
        port=LegacyCacheConfig.PORT,
        database=LegacyCacheConfig.DATABASE_NAME,
        user=LegacyCacheConfig.USER_R,
        password=LegacyCacheConfig.PWD_R
    )
    print("Connection successful!")
    conn.close()
except Exception as e:
    print(f"Connection failed: {e}")
```

### Issue: Data not found in new system

Check if dual-write was enabled:
```bash
echo $ENABLE_DUAL_WRITE_CACHE
```

If not, data needs to be migrated manually.

### Issue: Performance degradation

Check which backend is active:
```python
from sim2l.database.legacy_cache_adapter import LegacyCacheConfig
print(f"Using legacy backend: {LegacyCacheConfig.USE_LEGACY_BACKEND}")
```

New system should be faster for most operations.

---

## Complete Migration Checklist

- [ ] Review current cache usage in codebase
- [ ] Set up new cache service (Docker or standalone)
- [ ] Configure environment variables
- [ ] Test adapter with legacy backend enabled
- [ ] Enable dual-write mode
- [ ] Verify writes going to both systems
- [ ] Monitor for errors
- [ ] Switch reads to new system
- [ ] Verify read performance
- [ ] Run data migration script if needed
- [ ] Disable dual-write mode
- [ ] Disable legacy backend
- [ ] Remove legacy database credentials from environment
- [ ] Update documentation
- [ ] Remove legacy adapter code (optional, future)

---

## Support

For issues with migration:
1. Check environment variables are set correctly
2. Verify cache service is running (`curl http://localhost:8001/health`)
3. Check logs for errors
4. Review [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) for new system details

---

## Conclusion

The legacy cache adapter provides a smooth migration path from the old PostgreSQL-based cache to the new distributed cache system. Choose the migration strategy that best fits your requirements:

- **Direct cutover**: Clean, fast, for new projects
- **Dual-write**: Safe, zero-downtime, for production
- **Read-through**: Preserves data, gradual migration

With proper configuration, the migration can be completely transparent to application code.
