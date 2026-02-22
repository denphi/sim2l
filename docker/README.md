# Sim2l Database Services - Docker Setup

This directory contains Docker configurations for running sim2l database services.

## Quick Start

### Development (SQLite backends)

```bash
# Start cache and catalog services with SQLite
docker-compose --profile dev up -d

# Services will be available at:
# - Cache: http://localhost:8001
# - Catalog: http://localhost:8002

# Check health
curl http://localhost:8001/health
curl http://localhost:8002/health

# Stop services
docker-compose --profile dev down
```

### Production (PostgreSQL backends)

```bash
# Start all services including PostgreSQL
docker-compose --profile prod up -d

# Services will be available at:
# - PostgreSQL: localhost:5432
# - Cache: http://localhost:8001
# - Catalog: http://localhost:8002

# Check health
curl http://localhost:8001/health
curl http://localhost:8002/health

# View logs
docker-compose logs -f cache-postgres
docker-compose logs -f catalog-postgres

# Stop services
docker-compose --profile prod down
```

### Integration Tests (PostgreSQL only)

From the repository root:

```bash
./start_postgres_services.sh
python3 -m pytest -vv sim2l/tests/test_postgres_catalog_integration.py
python3 -m pytest -vv tests/test_catalog_postgres_backend_integration.py
./stop_postgres_services.sh
```

The startup script ensures these databases exist:
- `sim2l_cache`
- `sim2l_catalog`
- `sim2l_results`
- `sim2l_test`

If `localhost:5432` already has a reachable PostgreSQL instance, the script reuses it.

## Service Modes

### SQLite Mode (Development)
- **Pros**: Simple, no external database needed, portable
- **Cons**: Single-server only, no concurrent writes
- **Use for**: Local development, testing, single-user

### PostgreSQL Mode (Production)
- **Pros**: High concurrency, distributed, scalable
- **Cons**: Requires PostgreSQL server
- **Use for**: Multi-user environments, production deployments

## Configuration

### Environment Variables

#### Cache Service
- `BACKEND`: `sqlite` or `postgresql`
- `DB_PATH`: Path for SQLite database (SQLite mode)
- `DB_URL`: PostgreSQL connection string (PostgreSQL mode)
- `HOST`: Host to bind to (default: `0.0.0.0`)
- `PORT`: Port to listen on (default: `8001`)

#### Catalog Service
- `BACKEND`: `sqlite` or `postgresql`
- `DB_PATH`: Path for SQLite database (SQLite mode)
- `DB_URL`: PostgreSQL connection string (PostgreSQL mode)
- `HOST`: Host to bind to (default: `0.0.0.0`)
- `PORT`: Port to listen on (default: `8002`)

### Custom Configuration

Create a `.env` file:

```bash
# PostgreSQL
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_DB=sim2l

# Cache service
CACHE_PORT=8001
CACHE_DB_URL=postgresql://myuser:mypassword@postgres:5432/sim2l_cache

# Catalog service
CATALOG_PORT=8002
CATALOG_DB_URL=postgresql://myuser:mypassword@postgres:5432/sim2l_catalog
```

Then use it:

```bash
docker-compose --env-file .env --profile prod up -d
```

## Building Images

### Build cache service

```bash
docker build -f docker/Dockerfile.cache -t sim2l-cache:latest ..
```

### Build catalog service

```bash
docker build -f docker/Dockerfile.catalog -t sim2l-catalog:latest ..
```

## Running Individual Services

### Cache service only

```bash
# SQLite
docker run -d \
  -p 8001:8001 \
  -v cache_data:/data \
  -e BACKEND=sqlite \
  -e DB_PATH=/data/cache.db \
  sim2l-cache:latest

# PostgreSQL
docker run -d \
  -p 8001:8001 \
  -e BACKEND=postgresql \
  -e DB_URL=postgresql://user:password@dbhost:5432/sim2l_cache \
  sim2l-cache:latest
```

### Catalog service only

```bash
# SQLite
docker run -d \
  -p 8002:8002 \
  -v catalog_data:/data \
  -e BACKEND=sqlite \
  -e DB_PATH=/data/catalog.db \
  sim2l-catalog:latest

# PostgreSQL
docker run -d \
  -p 8002:8002 \
  -e BACKEND=postgresql \
  -e DB_URL=postgresql://user:password@dbhost:5432/sim2l_catalog \
  sim2l-catalog:latest
```

## Volumes

The compose setup creates persistent volumes:

- `postgres_data`: PostgreSQL database files
- `cache_data`: SQLite cache database (SQLite mode)
- `catalog_data`: SQLite catalog database (SQLite mode)

### Backup volumes

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U sim2l sim2l_cache > cache_backup.sql
docker-compose exec postgres pg_dump -U sim2l sim2l_catalog > catalog_backup.sql

# Backup SQLite
docker cp $(docker-compose ps -q cache-sqlite):/data/cache.db ./cache_backup.db
docker cp $(docker-compose ps -q catalog-sqlite):/data/catalog.db ./catalog_backup.db
```

### Restore volumes

```bash
# Restore PostgreSQL
cat cache_backup.sql | docker-compose exec -T postgres psql -U sim2l sim2l_cache
cat catalog_backup.sql | docker-compose exec -T postgres psql -U sim2l sim2l_catalog

# Restore SQLite
docker cp ./cache_backup.db $(docker-compose ps -q cache-sqlite):/data/cache.db
docker cp ./catalog_backup.db $(docker-compose ps -q catalog-sqlite):/data/catalog.db
```

## Networking

By default, services are accessible via:

| Service | Default Port | URL |
|---------|--------------|-----|
| Cache | 8001 | http://localhost:8001 |
| Catalog | 8002 | http://localhost:8002 |
| PostgreSQL | 5432 | postgresql://localhost:5432 |

### Custom ports

Modify the `ports` section in `docker-compose.yml`:

```yaml
cache-postgres:
  ports:
    - "9001:8001"  # Map host port 9001 to container port 8001
```

## Health Checks

All services expose a `/health` endpoint:

```bash
# Check cache service
curl http://localhost:8001/health

# Expected response:
# {
#   "status": "healthy",
#   "backend": "postgresql"
# }

# Check catalog service
curl http://localhost:8002/health

# Expected response:
# {
#   "status": "healthy",
#   "backend": "postgresql",
#   "simulations": 42
# }
```

## Scaling

### Horizontal scaling (PostgreSQL mode only)

```bash
# Scale cache service to 3 replicas
docker-compose --profile prod up -d --scale cache-postgres=3

# Use load balancer (nginx, traefik, etc.) to distribute requests
```

Note: SQLite mode does not support horizontal scaling.

## Troubleshooting

### Service won't start

```bash
# Check logs
docker-compose logs cache-postgres
docker-compose logs catalog-postgres

# Common issues:
# - PostgreSQL not ready (wait for health check)
# - Port already in use (change port mapping)
# - Database connection error (check DB_URL)
```

### PostgreSQL connection refused

```bash
# Ensure PostgreSQL is healthy
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Test connection manually
docker-compose exec postgres psql -U sim2l -d sim2l_cache
```

### Reset everything

```bash
# Stop and remove all containers, volumes, and images
docker-compose --profile prod down -v --rmi all

# Start fresh
docker-compose --profile prod up -d
```

## Client Configuration

### Using Docker services from Python

```python
from sim2l import configure

# Configure to use Docker services
configure(
    use_run_database=True,
    cache_service_url="http://localhost:8001",
    catalog_service_url="http://localhost:8002",
)
```

### Using environment variables

```bash
export SIM2L_CACHE_SERVICE_URL=http://localhost:8001
export SIM2L_CATALOG_SERVICE_URL=http://localhost:8002
export SIM2L_USE_RUN_DATABASE=true

# Run your sim2l code
python my_simulation.py
```

## Production Deployment

### Recommended setup

1. **Use PostgreSQL backend** for both services
2. **Enable SSL/TLS** for database connections
3. **Use reverse proxy** (nginx, traefik) for HTTPS
4. **Set up monitoring** (Prometheus, Grafana)
5. **Configure backups** (automated pg_dump)
6. **Use secrets management** (Docker Secrets, Vault)

### Example with Docker Secrets

```yaml
services:
  cache-postgres:
    environment:
      DB_URL_FILE: /run/secrets/cache_db_url
    secrets:
      - cache_db_url

secrets:
  cache_db_url:
    external: true
```

```bash
echo "postgresql://user:password@postgres:5432/sim2l_cache" | \
  docker secret create cache_db_url -
```

## Monitoring

### Service metrics

```bash
# Cache statistics
curl http://localhost:8001/cache/stats

# Catalog statistics
curl http://localhost:8002/simulations/search?status=active
```

### Database metrics

```bash
# PostgreSQL stats
docker-compose exec postgres psql -U sim2l -c "\
  SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del \
  FROM pg_stat_user_tables;"
```

## Support

For issues and questions:
- GitHub Issues: [sim2l repository]
- Documentation: [DATABASE_ARCHITECTURE.md]
- Docker Hub: [sim2l images]
