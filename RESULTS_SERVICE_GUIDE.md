## Results Service Guide

The Results Service is the modern replacement for `registerSquidpgSimtool`. It introspects simulation runs, extracts parameter schemas and values, and stores them in a searchable database.

---

## Quick Start

### Starting the Service

```bash
# SQLite backend (default)
python -m sim2l.services.results_service --port 8003

# PostgreSQL backend (production)
python -m sim2l.services.results_service \
    --backend postgresql \
    --db-url "postgresql://user:pass@localhost/sim2l_results" \
    --port 8003
```

### Using the Client

```python
from sim2l.database import ResultsClient, get_session_manager

# Create session
session = get_session_manager().create_anonymous_session()

# Connect to service
client = ResultsClient(
    "http://localhost:8003",
    session_id=session.session_id
)

# Register a result
client.register_result("exec-2024-001")

# Search for results
results = client.search(
    simulation_name="thermal_sim",
    input_filters={'temperature': 350}
)

# Get parameter statistics
stats = client.get_parameter_stats(
    "thermal_sim",
    "max_stress",
    param_class="output"
)
```

---

## What Gets Introspected

When you register a result, the service automatically extracts:

### From Run Database

1. **Simulation Metadata**
   - Simulation name and version
   - Execution ID and SQUID ID
   - Status and duration

2. **Input Parameters**
   - Parameter name, type, value
   - Units, min/max, defaults
   - Description and label

3. **Output Parameters**
   - Parameter name, type, value
   - Units and description
   - Computed results

### Parameter Schema

The service builds a schema for each simulation tool/version:

```json
{
  "input": {
    "temperature": {
      "type": "number",
      "label": "Temperature",
      "description": "Operating temperature",
      "units": "kelvin",
      "min": 273,
      "max": 400,
      "default": 300
    },
    "pressure": {
      "type": "number",
      "label": "Pressure",
      "units": "pascal",
      "default": 101325
    }
  },
  "output": {
    "max_stress": {
      "type": "number",
      "label": "Maximum Stress",
      "units": "pascal"
    }
  }
}
```

### Parameter Values

For each execution, actual parameter values are stored:

```json
{
  "input_params": {
    "temperature": 350,
    "pressure": 101325
  },
  "output_params": {
    "max_stress": 1.5e8
  }
}
```

---

## Core Features

### 1. Result Registration

Register a simulation result to make it searchable:

```python
client = ResultsClient("http://localhost:8003", session_id=session.session_id)

# Basic registration
result = client.register_result("exec-2024-001")
print(f"Result ID: {result['result_id']}")
print(f"Schema ID: {result['schema_id']}")

# With custom SQUID ID
result = client.register_result(
    "exec-2024-001",
    squid_id="thermal_sim/v1.0/run-001"
)

# With metadata
result = client.register_result(
    "exec-2024-001",
    metadata={
        'project': 'materials_research',
        'operator': 'alice'
    }
)
```

**What Happens**:
1. Service reads the run database
2. Extracts input/output parameters
3. Builds or updates the parameter schema
4. Stores parameter values
5. Returns IDs for the result and schema

### 2. Search by Parameters

Find results matching specific parameter values:

```python
# Search by input parameters
results = client.search(
    simulation_name="thermal_sim",
    input_filters={
        'temperature': 350,
        'pressure': 101325
    }
)

# Search by output parameters
results = client.search(
    simulation_name="thermal_sim",
    output_filters={
        'max_stress': 1.5e8
    }
)

# Search by both
results = client.search(
    simulation_name="thermal_sim",
    input_filters={'temperature': 350},
    output_filters={'max_stress': 1.5e8},
    limit=50
)

# Process results
for result in results:
    print(f"Execution: {result['execution_id']}")
    print(f"  Inputs: {result['input_params']}")
    print(f"  Outputs: {result['output_params']}")
    print(f"  Status: {result['status']}")
```

**Search Capabilities**:
- Exact match on parameter values
- Filter by simulation name/version
- Combine input and output filters
- Limit number of results

### 3. Parameter Statistics

Get statistical information for parameters across all runs:

```python
# Get statistics for an output parameter
stats = client.get_parameter_stats(
    simulation_name="thermal_sim",
    param_name="max_stress",
    param_class="output"
)

if stats['count'] > 0:
    print(f"Parameter: {stats['param_name']}")
    print(f"Runs analyzed: {stats['count']}")
    print(f"Min value: {stats['min_value']}")
    print(f"Max value: {stats['max_value']}")
    print(f"Average: {stats['avg_value']}")

# Get statistics for an input parameter
stats = client.get_parameter_stats(
    simulation_name="thermal_sim",
    param_name="temperature",
    param_class="input"
)
```

**Use Cases**:
- Understand parameter ranges
- Validate simulation results
- Identify outliers
- Optimize parameter selection

### 4. Get Specific Result

Retrieve complete information for a specific execution:

```python
result = client.get_result("exec-2024-001")

if result:
    print(f"Simulation: {result['simulation_name']} v{result['simulation_version']}")
    print(f"Status: {result['status']}")
    print(f"Duration: {result['duration_seconds']}s")
    print(f"Run DB: {result['run_db_path']}")

    print("\nInput Parameters:")
    for key, value in result['input_params'].items():
        print(f"  {key}: {value}")

    print("\nOutput Parameters:")
    for key, value in result['output_params'].items():
        print(f"  {key}: {value}")
```

---

## Deployment

### SQLite Backend (Development)

```bash
# Start service
python -m sim2l.services.results_service \
    --backend sqlite \
    --db-path ~/.sim2l/results.db \
    --port 8003
```

**Pros**:
- No database server required
- Fast for small datasets
- Easy setup

**Cons**:
- Not suitable for high concurrency
- Limited search capabilities
- Single-server only

### PostgreSQL Backend (Production)

```bash
# Start service
python -m sim2l.services.results_service \
    --backend postgresql \
    --db-url "postgresql://user:pass@localhost/sim2l_results" \
    --port 8003
```

**Pros**:
- High concurrency support
- Advanced search with JSONB indexes
- Stored procedures for complex queries
- Horizontal scaling

**Cons**:
- Requires PostgreSQL server
- More complex setup

### Docker Deployment

Add to `docker-compose.yml`:

```yaml
services:
  results-service:
    build:
      context: .
      dockerfile: docker/Dockerfile.results
    ports:
      - "8003:8003"
    environment:
      - RESULTS_BACKEND=postgresql
      - RESULTS_DB_URL=postgresql://user:pass@postgres/sim2l_results
    depends_on:
      - postgres
```

---

## API Reference

### POST /register

Register a simulation result.

**Request**:
```json
{
  "execution_id": "exec-2024-001",
  "squid_id": "thermal_sim/v1.0/run-001",
  "metadata": {
    "project": "materials_research"
  }
}
```

**Response**:
```json
{
  "success": true,
  "result_id": 123,
  "schema_id": 45
}
```

**Headers**:
- `X-Session-ID`: Session ID for authentication

### POST /search

Search for results by parameter values.

**Request**:
```json
{
  "simulation_name": "thermal_sim",
  "input_filters": {
    "temperature": 350
  },
  "output_filters": {
    "max_stress": 1.5e8
  },
  "limit": 100
}
```

**Response**:
```json
{
  "results": [
    {
      "execution_id": "exec-2024-001",
      "simulation_name": "thermal_sim",
      "simulation_version": "1.0.0",
      "squid_id": "thermal_sim/v1.0/run-001",
      "input_params": {"temperature": 350},
      "output_params": {"max_stress": 1.5e8},
      "status": "completed",
      "created_at": "2024-01-01T12:00:00"
    }
  ],
  "count": 1
}
```

### GET /results/{execution_id}

Get a specific result.

**Response**:
```json
{
  "id": 123,
  "execution_id": "exec-2024-001",
  "simulation_name": "thermal_sim",
  "simulation_version": "1.0.0",
  "squid_id": "thermal_sim/v1.0/run-001",
  "input_params": {"temperature": 350},
  "output_params": {"max_stress": 1.5e8},
  "status": "completed",
  "duration_seconds": 42.5,
  "created_at": "2024-01-01T12:00:00",
  "completed_at": "2024-01-01T12:00:42",
  "run_db_path": "/path/to/run.db",
  "metadata": {}
}
```

### GET /stats/{simulation_name}/{param_name}

Get parameter statistics.

**Query Parameters**:
- `class`: 'input' or 'output' (default: 'output')

**Response**:
```json
{
  "param_name": "max_stress",
  "param_type": "number",
  "min_value": 1.0e8,
  "max_value": 2.0e8,
  "avg_value": 1.5e8,
  "count": 100
}
```

### GET /health

Health check.

**Response**:
```json
{
  "status": "healthy",
  "service": "results",
  "backend": "postgresql"
}
```

---

## Common Workflows

### Workflow 1: Post-Simulation Registration

```python
from sim2l.database import ResultsClient, get_session_manager

def register_after_run(execution_id):
    """Register result immediately after simulation completes."""

    # Authenticate
    session = get_session_manager().create_anonymous_session()

    # Connect to service
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    # Register result
    try:
        result = client.register_result(execution_id)
        print(f"✓ Registered: {result['result_id']}")
        return True
    except Exception as e:
        print(f"✗ Registration failed: {e}")
        return False

# Use in your simulation code
# result = sim.run(...)
# register_after_run(result.execution_id)
```

### Workflow 2: Batch Registration

```python
def register_historical_runs(execution_ids):
    """Register multiple historical runs."""

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    success = 0
    failed = 0

    for exec_id in execution_ids:
        try:
            client.register_result(exec_id)
            success += 1
            print(f"✓ {exec_id}")
        except Exception as e:
            failed += 1
            print(f"✗ {exec_id}: {e}")

    print(f"\nRegistered: {success}/{len(execution_ids)}")
    print(f"Failed: {failed}")
```

### Workflow 3: Parameter Sweep Analysis

```python
def analyze_parameter_sweep(simulation_name, param_name):
    """Analyze results from a parameter sweep."""

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    # Get statistics
    stats = client.get_parameter_stats(
        simulation_name,
        param_name,
        param_class="output"
    )

    print(f"Parameter: {param_name}")
    print(f"Runs: {stats['count']}")
    print(f"Range: {stats['min_value']} - {stats['max_value']}")
    print(f"Average: {stats['avg_value']}")

    # Find optimal results (example: minimize max_stress)
    results = client.search(simulation_name=simulation_name)

    # Sort by output parameter
    sorted_results = sorted(
        results,
        key=lambda r: r['output_params'].get(param_name, float('inf'))
    )

    print(f"\nTop 5 results:")
    for i, result in enumerate(sorted_results[:5], 1):
        print(f"{i}. {result['execution_id']}: {result['output_params'][param_name]}")
        print(f"   Inputs: {result['input_params']}")
```

---

## Comparison with Legacy registerSquidpgSimtool

| Feature | Legacy | Results Service |
|---------|--------|-----------------|
| Parameter extraction | Manual | Automatic |
| Database | PostgreSQL only | SQLite + PostgreSQL |
| API | Script-based | REST API |
| Authentication | DB credentials | Session-based |
| Search | SQL queries | REST endpoints |
| Statistics | Manual | Built-in |
| Deployment | Server-side script | Microservice |
| Integration | Tight coupling | Loose coupling |

### Migration from Legacy

```python
# Old way (registerSquidpgSimtool)
# $ registerSquidpgSimtool -s "tool/r1/squid-123"

# New way (Results Service)
from sim2l.database import ResultsClient, get_session_manager

session = get_session_manager().create_anonymous_session()
client = ResultsClient("http://localhost:8003", session_id=session.session_id)

client.register_result(
    execution_id="exec-123",
    squid_id="tool/r1/squid-123"
)
```

---

## Best Practices

### 1. Register Results Automatically

Integrate registration into your simulation workflow:

```python
from sim2l import configure
from sim2l.database import ResultsClient, get_session_manager

# Configure sim2l
session = get_session_manager().create_anonymous_session()
configure(
    use_run_database=True,
    results_service_url="http://localhost:8003",
    results_session_id=session.session_id,
    results_auto_register=True  # Auto-register after each run
)

# Run simulation - result is automatically registered
result = sim.run(temperature=350)
```

### 2. Use Meaningful SQUID IDs

```python
# Good - structured and searchable
squid_id = f"{sim_name}/{version}/{date}/{run_number}"

# Better - include parameter info
squid_id = f"{sim_name}/{version}/T{temperature}_P{pressure}/{run_number}"

client.register_result(execution_id, squid_id=squid_id)
```

### 3. Add Contextual Metadata

```python
client.register_result(
    execution_id,
    metadata={
        'project': 'materials_research',
        'operator': 'alice',
        'purpose': 'parameter_sweep',
        'batch_id': 'batch-2024-001'
    }
)
```

### 4. Handle Registration Errors

```python
try:
    client.register_result(execution_id)
except Exception as e:
    # Log error but don't fail the simulation
    logger.error(f"Result registration failed: {e}")
    # Optionally retry later
```

---

## Troubleshooting

### Service Not Starting

```bash
# Check if port is in use
lsof -i :8003

# Check database connectivity (PostgreSQL)
psql -h localhost -U user -d sim2l_results

# View service logs
python -m sim2l.services.results_service --backend sqlite 2>&1 | tee results.log
```

### Registration Fails

```python
# Check if run database exists
from sim2l.database import RunDatabase

try:
    run_db = RunDatabase(execution_id)
    print("Run database exists")
except Exception as e:
    print(f"Run database error: {e}")

# Check service health
health = client.health_check()
print(f"Service status: {health}")
```

### Search Returns No Results

```python
# Verify result is registered
result = client.get_result(execution_id)
if result:
    print("Result is registered")
    print(f"Input params: {result['input_params']}")
    print(f"Output params: {result['output_params']}")
else:
    print("Result not found - needs registration")
```

---

## Summary

The Results Service provides:

✅ **Automatic introspection** of simulation results
✅ **Searchable storage** of parameter values
✅ **REST API** for programmatic access
✅ **Parameter statistics** across runs
✅ **Dual backend** support (SQLite/PostgreSQL)
✅ **Session-based authentication**
✅ **Modern replacement** for registerSquidpgSimtool

Use it to make your simulation results discoverable and queryable!
