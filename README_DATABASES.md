# Sim2l Database Systems

Three integrated database systems for simulation management, caching, and cataloging.

## 🚀 Quick Start

### Option 1: Local Mode (No Services)

```python
from sim2l import configure

# Enable per-run databases
configure(use_run_database=True)

# Your existing code works unchanged
result = sim.run(param=100)

# Access complete run database
from sim2l.database import RunDatabase
run_db = RunDatabase(result.execution_id)
print(run_db.get_summary())
```

### Option 2: With Services (Docker)

```bash
# Start cache and catalog services
cd docker
docker-compose --profile dev up -d

# Services now running at:
# - Cache: http://localhost:8001
# - Catalog: http://localhost:8002
```

```python
from sim2l import configure
from sim2l.database import get_session_manager

# Create session
session = get_session_manager().create_anonymous_session()

# Configure services
configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    cache_session_id=session.session_id,
    catalog_service_url="http://localhost:8002",
    catalog_session_id=session.session_id
)

# Everything automated!
result = sim.run(param=100)
```

## 📚 Documentation

- **[QUICKSTART_DATABASES.md](QUICKSTART_DATABASES.md)** - Get started in 5 minutes
- **[DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md)** - Complete technical reference
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Implementation details
- **[docker/README.md](docker/README.md)** - Docker deployment guide

## 🎯 What You Get

### 1. Per-Run SQLite Databases

Each execution gets its own database containing:
- ✅ All inputs and outputs
- ✅ Complete logs with context
- ✅ Files and artifacts
- ✅ Performance metrics
- ✅ Resource usage
- ✅ Provenance tracking

**Benefits**: Complete isolation, portability, easy debugging

### 2. Cache Service

Distributed caching with:
- ✅ Automatic deduplication
- ✅ Session-based auth
- ✅ Cache invalidation
- ✅ Statistics
- ✅ REST API

**Benefits**: Team-wide cache sharing, faster execution, analytics

### 3. Catalog Service

Central tool registry with:
- ✅ Tool discovery and search
- ✅ Version management
- ✅ Execution statistics
- ✅ Auto-sync
- ✅ Access control

**Benefits**: Centralized tool management, discoverability, governance

## 🔧 Key Features

- **Dual Backend**: SQLite (dev) + PostgreSQL (prod)
- **Flexible Deployment**: Local, Docker, or hybrid
- **Session Auth**: Role-based access control
- **REST APIs**: Standard HTTP/JSON interfaces
- **CLI Tools**: Service management commands
- **Comprehensive Tests**: Full test suite included

## 📦 Installation

```bash
# Install sim2l
pip install sim2l

# Optional: Install PostgreSQL support
pip install psycopg2-binary

# Optional: Install Docker for services
# (Docker installation varies by platform)
```

## 🎬 Usage Examples

### Example 1: Debug a Failed Run

```python
from sim2l.database import RunDatabase

# Open run database from failed execution
run_db = RunDatabase("failed-execution-id")

# Get error details
errors = run_db.get_errors()
for error in errors:
    print(f"{error['timestamp']}: {error['message']}")
    print(f"Stack trace: {error['stack_trace']}")

# Check what inputs were used
inputs = run_db.get_inputs()
print(f"Inputs: {inputs}")
```

### Example 2: Share Results

```bash
# Run database is a single file
cd ~/.sim2l/runs
ls -lh abc-123.db  # ~5 MB

# Email or share this file
# Colleague can query it directly
```

```python
# Colleague's machine
from sim2l.database import RunDatabase

run_db = RunDatabase.from_file("received-run.db")
outputs = run_db.get_outputs()
summary = run_db.get_summary()
```

### Example 3: Team Cache

```python
from sim2l.database import CacheClient

cache = CacheClient("http://team-cache:8001", session_id="...")

# Check cache before expensive run
cached = cache.get(cache_key)
if cached:
    print(f"Cache hit! Using execution: {cached['execution_id']}")
else:
    result = sim.run(...)  # Run and cache

# Invalidate after bug fix
cache.invalidate(
    simulation_name="my_sim",
    simulation_version="1.0.0",
    reason="Bug fix in v1.0.1"
)
```

### Example 4: Discover Tools

```python
from sim2l.database import CatalogClient

catalog = CatalogClient("http://catalog:8002", session_id="...")

# Search for simulations
results = catalog.search(query="thermal", tags=["physics"])
for sim in results:
    print(f"{sim['name']} v{sim['version']}")
    print(f"  Author: {sim['author']}")
    print(f"  Runs: {sim['total_executions']}")
    print(f"  Cache hit rate: {sim['cache_hit_rate']}%")
```

## 🐳 Docker Deployment

```bash
# Development (SQLite backends)
docker-compose --profile dev up -d

# Production (PostgreSQL backends)
docker-compose --profile prod up -d

# Check health
curl http://localhost:8001/health
curl http://localhost:8002/health

# Stop services
docker-compose down
```

## 🔐 Security

All services include:
- Session-based authentication
- Role-based access control (user, developer, admin)
- Privilege checking for operations
- Audit logging
- Password hashing

## 📊 Monitoring

```bash
# Cache statistics
curl http://localhost:8001/cache/stats

# Catalog statistics
curl http://localhost:8002/simulations/search?status=active

# Health checks
sim2l services health
```

## 🧪 Testing

```bash
# Run integration tests
pytest tests/test_database_integration.py -v

# Test specific component
pytest tests/test_database_integration.py::TestRunDatabase -v
```

## 🛠️ CLI Commands

```bash
# Start cache service
sim2l services cache start --backend sqlite --port 8001 --daemon

# Check status
sim2l services cache status

# Get statistics
sim2l services cache stats

# Start catalog service
sim2l services catalog start --backend postgresql --db-url=...

# Search catalog
sim2l services catalog search thermal --tags physics

# Health check all services
sim2l services health
```

## 🗂️ Project Structure

```
sim2l/
├── database/              # Database implementations
│   ├── run_database.py       # Per-run SQLite
│   ├── cache_client.py       # Cache service client
│   ├── catalog_client.py     # Catalog service client
│   ├── session_manager.py    # Authentication
│   └── *.sql                 # Database schemas
├── services/              # REST API services
│   ├── cache_service.py      # Cache REST API
│   └── catalog_service.py    # Catalog REST API
├── cli/                   # Command-line tools
│   └── services.py           # Service management
├── docker/                # Docker deployment
│   ├── Dockerfile.*
│   ├── docker-compose.yml
│   └── README.md
├── tests/                 # Integration tests
│   └── test_database_integration.py
└── docs/
    ├── DATABASE_ARCHITECTURE.md
    ├── QUICKSTART_DATABASES.md
    ├── IMPLEMENTATION_SUMMARY.md
    └── README_DATABASES.md (this file)
```

## 🔗 Links

- **Documentation**: See docs/ directory
- **Examples**: tests/test_database_integration.py
- **Docker**: docker/README.md
- **Issues**: GitHub issue tracker

## 📈 Roadmap

### ✅ Completed
- Per-run SQLite databases
- Session management
- Cache service (SQLite + PostgreSQL)
- Catalog service (SQLite)
- Docker deployment
- CLI commands
- Comprehensive tests

### 🚧 In Progress
- Executor integration
- Catalog PostgreSQL backend
- Performance optimization

### 🔮 Planned
- Web UI for catalog
- Metrics dashboard
- Redis cache backend
- S3 artifact storage
- Advanced analytics

## 🤝 Contributing

1. Read [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) for architecture details
2. Check [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for code structure
3. Run tests: `pytest tests/ -v`
4. Follow existing code style
5. Add tests for new features

## 📄 License

Same license as sim2l project.

## 💬 Support

- **Questions**: GitHub Discussions
- **Issues**: GitHub Issues
- **Documentation**: See docs/ directory

---

**Status**: Production-ready for per-run databases, cache service, and catalog service (SQLite). PostgreSQL catalog backend and executor integration in progress.

**Version**: 1.0.0-beta

**Last Updated**: 2024
