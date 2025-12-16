# Sim2l Services

Local testing and development scripts for sim2l database services.

## Quick Start

### Start All Services

```bash
./start_services.sh
```

This starts three services:
- **Cache Service** on port 8001
- **Catalog Service** on port 8002
- **Results Service** on port 8003

All services use SQLite backends for local testing.

### Stop All Services

```bash
./stop_services.sh
```

### Test Services

```bash
python3 test_services.py
```

## Service Details

### Cache Service (Port 8001)

Distributed caching for simulation results.

**Health Check**:
```bash
curl http://localhost:8001/health
```

**Store Cache Entry**:
```bash
curl -X POST http://localhost:8001/cache \
  -H "Content-Type: application/json" \
  -d '{
    "cache_key": "test/key",
    "simulation_id": 1,
    "simulation_name": "test_sim",
    "simulation_version": "1.0.0",
    "execution_id": "exec-001",
    "squid_id": "test/1.0.0/001",
    "input_hash": "hash123",
    "run_db_path": "/path/to/run.db"
  }'
```

**Retrieve Cache Entry**:
```bash
curl http://localhost:8001/cache/test/key
```

### Catalog Service (Port 8002)

Central registry for simulation tools.

**Health Check**:
```bash
curl http://localhost:8002/health
```

**Register Simulation**:
```bash
curl -X POST http://localhost:8002/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "thermal_sim",
    "version": "1.0.0",
    "description": "Thermal stress analysis",
    "tags": ["thermal", "physics"],
    "schema": {}
  }'
```

**Search Simulations**:
```bash
curl "http://localhost:8002/simulations/search?query=thermal"
```

### Results Service (Port 8003)

Introspects and indexes simulation results.

**Health Check**:
```bash
curl http://localhost:8003/health
```

**Register Result** (requires execution_id with run database):
```bash
curl -X POST http://localhost:8003/register \
  -H "Content-Type: application/json" \
  -d '{
    "execution_id": "exec-2024-001"
  }'
```

**Search Results**:
```bash
curl -X POST http://localhost:8003/search \
  -H "Content-Type: application/json" \
  -d '{
    "simulation_name": "thermal_sim",
    "input_filters": {"temperature": 350}
  }'
```

## Logs

Service logs are written to `~/.sim2l/logs/`:
- `cache.log` - Cache service logs
- `catalog.log` - Catalog service logs
- `results.log` - Results service logs

**View all logs**:
```bash
tail -f ~/.sim2l/logs/*.log
```

**View specific service**:
```bash
tail -f ~/.sim2l/logs/cache.log
```

## Databases

Service databases are stored in `~/.sim2l/`:
- `cache.db` - Cache service SQLite database
- `catalog.db` - Catalog service SQLite database
- `results.db` - Results service SQLite database

**Clean databases** (removes all data):
```bash
rm ~/.sim2l/*.db
```

## Python Usage

### Using the Services

```python
from sim2l import configure
from sim2l.database import (
    CacheClient,
    CatalogClient,
    ResultsClient,
    get_session_manager
)

# Create session (for auth in production)
session = get_session_manager().create_anonymous_session()

# Configure sim2l
configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    cache_session_id=session.session_id,
    catalog_service_url="http://localhost:8002",
    catalog_session_id=session.session_id
)

# Use cache
cache = CacheClient("http://localhost:8001", session_id=session.session_id)
cache.set(
    cache_key="test/key",
    simulation_id=1,
    simulation_name="test_sim",
    simulation_version="1.0.0",
    execution_id="exec-001",
    squid_id="test/1.0.0/001",
    input_hash="hash123",
    run_db_path="/path/to/run.db"
)

result = cache.get("test/key")
print(result)

# Use catalog
catalog = CatalogClient("http://localhost:8002", session_id=session.session_id)
catalog.register_simulation(
    name="thermal_sim",
    version="1.0.0",
    description="Thermal stress analysis",
    tags=["thermal", "physics"],
    schema={}
)

sims = catalog.search(query="thermal")
print(f"Found {len(sims)} simulations")

# Use results service
results_client = ResultsClient("http://localhost:8003", session_id=session.session_id)
# Register a result (requires run database to exist)
# results_client.register_result("exec-2024-001")
```

## Troubleshooting

### Services Won't Start

Check if ports are in use:
```bash
lsof -i :8001
lsof -i :8002
lsof -i :8003
```

Kill processes on these ports if needed:
```bash
kill -9 $(lsof -t -i:8001)
kill -9 $(lsof -t -i:8002)
kill -9 $(lsof -t -i:8003)
```

### Services Not Responding

1. **Check if services are running**:
   ```bash
   ps aux | grep "sim2l.services"
   ```

2. **Check logs**:
   ```bash
   cat ~/.sim2l/logs/cache.log
   cat ~/.sim2l/logs/catalog.log
   cat ~/.sim2l/logs/results.log
   ```

3. **Restart services**:
   ```bash
   ./stop_services.sh
   ./start_services.sh
   ```

### Database Errors

If you see database errors, try cleaning and restarting:
```bash
./stop_services.sh
rm ~/.sim2l/*.db
./start_services.sh
```

## Production Deployment

For production deployment, see:
- [Docker Deployment](../docker/README.md)
- [Documentation](../docs/deployment.rst)

Production setup uses:
- PostgreSQL instead of SQLite
- Proper authentication with session management
- TLS/SSL encryption
- Load balancing
- Monitoring and logging

## Development

### Adding a New Service

1. Create service in `sim2l/services/new_service.py`
2. Add to `start_services.sh`
3. Add to `stop_services.sh`
4. Add health check to `test_services.py`
5. Update this README

### Running Tests

```bash
# Test all services
python3 test_services.py

# Manual health checks
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

## See Also

- [Database Services Documentation](../docs/database_services.rst)
- [Quick Start Guide](../docs/quickstart.rst)
- [Examples](../examples/)
