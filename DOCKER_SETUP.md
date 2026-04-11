# sim2l Docker Setup Guide

This guide explains the Docker setup for running sim2l backend services and the web UI dashboard.

## Overview

The project now includes a complete Docker setup that runs:
- **Backend Services**: Cache, Catalog, and Results services (SQLite or PostgreSQL)
- **Web UI**: React-based dashboard for monitoring and managing services
- **PostgreSQL**: Optional database for production deployments

## Changes Made

### 1. New Docker Files Created

#### Backend Services
- **`docker/Dockerfile.cache`** - Cache service container
- **`docker/Dockerfile.catalog`** - Catalog service container  
- **`docker/Dockerfile.results`** - Results service container (NEW)

All backend Dockerfiles:
- Use Python 3.11 slim base image
- Install dependencies from `requirements.txt`
- Copy the `sim2l` package
- Support both SQLite (development) and PostgreSQL (production) backends

#### Web UI
- **`docker/Dockerfile.web-ui`** - Multi-stage build for React web UI
  - Build stage: Node 18 Alpine, installs npm dependencies and builds the app
  - Production stage: Nginx Alpine, serves static files and proxies API requests
- **`docker/nginx.conf`** - Nginx configuration for routing and API proxying

### 2. Updated docker-compose.yml

Added new services:
- `results-sqlite` - Results service in SQLite mode (development)
- `results-postgres` - Results service in PostgreSQL mode (production)
- `web-ui` - Web dashboard for development mode
- `web-ui-prod` - Web dashboard for production mode

Network aliases added to all services so the web UI nginx can resolve them:
- `cache` → cache-sqlite or cache-postgres
- `catalog` → catalog-sqlite or catalog-postgres  
- `results` → results-sqlite or results-postgres

### 3. Backend API Updates

**File: `sim2l/services/cache_service.py`**

Changes:
- Added `json` import to support metadata serialization
- Updated `list_entries()` method in both SQLite and PostgreSQL backends to return `metadata` field
- The metadata contains input parameters for each cache entry

**What this enables:**
- Web UI can now display simulation input parameters in the cache view
- Parameters are shown inline in the table (first 2 params) with full details in expanded view

## Running the Project

### Prerequisites
- Docker Desktop installed and running
- At least 4GB RAM available for Docker
- Ports 3000, 8001, 8002, 8003, and 5432 available

### Development Mode (SQLite - Recommended for Development)

Start all services with SQLite backends:

```bash
cd docker
docker-compose --profile dev up -d
```

This starts:
- PostgreSQL (for future use)
- Cache service on port 8001 (SQLite)
- Catalog service on port 8002 (SQLite)
- Results service on port 8003 (SQLite)
- Web UI on port 3000

### Production Mode (PostgreSQL)

Start all services with PostgreSQL backends:

```bash
cd docker
docker-compose --profile prod up -d
```

This starts:
- PostgreSQL database on port 5432
- All three services connected to PostgreSQL
- Web UI on port 3000

### Building from Scratch

To rebuild all containers:

```bash
cd docker
docker-compose --profile dev build
docker-compose --profile dev up -d
```

### Stopping Services

```bash
cd docker
docker-compose --profile dev down
```

To also remove volumes (WARNING: deletes all data):

```bash
docker-compose --profile dev down -v
```

## Accessing Services

Once running, access:

- **Web UI Dashboard**: http://localhost:3000
- **Cache Service API**: http://localhost:8001
- **Catalog Service API**: http://localhost:8002
- **Results Service API**: http://localhost:8003
- **PostgreSQL**: localhost:5432 (if running prod mode)

### Web UI Features

The web dashboard provides:

1. **Dashboard** - Overview of all services with health status
2. **Cache View** - Browse cache entries with:
   - Simulation name, version, and SQUID ID
   - **Input parameters displayed in table** (new feature!)
   - Cache statistics and metrics
   - Ability to invalidate entries
3. **Catalog View** - Browse registered simulations
4. **Results View** - Search and explore execution results

### API Health Checks

Check service health:

```bash
# Cache service
curl http://localhost:8001/health

# Catalog service
curl http://localhost:8002/health

# Results service
curl http://localhost:8003/health
```

## Configuration

### Environment Variables

Each service supports these environment variables:

**Backend Services (cache, catalog, results):**
- `BACKEND`: `sqlite` or `postgresql`
- `DB_PATH`: Path for SQLite database (SQLite mode)
- `DB_URL`: PostgreSQL connection string (PostgreSQL mode)
- `HOST`: Host to bind to (default: `0.0.0.0`)
- `PORT`: Port to listen on

**Web UI:**
- Configured via `web-ui/.env` (for development)
- Uses nginx proxy in Docker (no env vars needed)

### Switching Between SQLite and PostgreSQL

The docker-compose.yml uses profiles:
- `dev` profile: SQLite backends (fast, simple)
- `prod` profile: PostgreSQL backends (production-ready, scalable)

### Nginx Proxy Configuration

The web UI uses nginx to proxy API requests:
- `/api/cache/` → `http://cache:8001/`
- `/api/catalog/` → `http://catalog:8002/`
- `/api/results/` → `http://results:8003/`

This avoids CORS issues and provides a unified endpoint.

## Troubleshooting

### Services Not Starting

Check logs for a specific service:

```bash
docker logs docker-cache-sqlite-1
docker logs docker-catalog-sqlite-1
docker logs docker-results-sqlite-1
docker logs docker-web-ui-1
```

### Port Already in Use

If ports are already in use, modify the port mappings in `docker-compose.yml`:

```yaml
ports:
  - "3001:3000"  # Change 3000 to 3001 for web UI
```

### Web UI Can't Connect to Services

1. Ensure all backend services are running:
   ```bash
   docker ps
   ```

2. Check service health:
   ```bash
   curl http://localhost:8001/health
   curl http://localhost:8002/health
   curl http://localhost:8003/health
   ```

3. Check web UI logs:
   ```bash
   docker logs docker-web-ui-1
   ```

### Container Fails with "ModuleNotFoundError"

This means dependencies weren't installed. Rebuild:

```bash
cd docker
docker-compose --profile dev build --no-cache
docker-compose --profile dev up -d
```

## File Structure

```
sim2l_updated_version/
├── docker/
│   ├── docker-compose.yml       # Orchestrates all services
│   ├── Dockerfile.cache         # Cache service
│   ├── Dockerfile.catalog       # Catalog service
│   ├── Dockerfile.results       # Results service (NEW)
│   ├── Dockerfile.web-ui        # Web UI multi-stage build (NEW)
│   ├── nginx.conf               # Nginx config for web UI (NEW)
│   ├── init-db.sql              # PostgreSQL initialization
│   └── README.md                # Docker documentation
├── web-ui/
│   ├── src/                     # React application source
│   ├── package.json             # Node dependencies
│   ├── vite.config.ts           # Vite configuration
│   └── .env                     # Environment variables (dev mode)
├── sim2l/
│   └── services/
│       ├── cache_service.py     # Updated with metadata support
│       ├── catalog_service.py
│       └── results_service.py
└── requirements.txt             # Python dependencies
```

## Development Workflow

### Making Backend Changes

1. Edit Python code in `sim2l/`
2. Rebuild the specific service:
   ```bash
   cd docker
   docker-compose --profile dev build cache-sqlite
   docker-compose --profile dev up -d cache-sqlite
   ```

### Making Frontend Changes

For live development without Docker:

```bash
cd web-ui
npm install
npm run dev
```

Access at http://localhost:3000 (Vite dev server with hot reload)

To update the Docker container:

```bash
cd docker
docker-compose --profile dev build web-ui
docker-compose --profile dev up -d web-ui
```

## Performance Considerations

- **First build**: Takes 3-5 minutes (downloading images, installing dependencies)
- **Subsequent builds**: Much faster due to Docker layer caching
- **SQLite mode**: Fast, suitable for development and single-user setups
- **PostgreSQL mode**: Better for production, supports concurrent users

## Next Steps

1. **Add authentication**: Implement proper session management
2. **Add SSL/TLS**: Configure HTTPS for production deployments
3. **Add monitoring**: Integrate Prometheus/Grafana for metrics
4. **Scale horizontally**: Run multiple replicas behind a load balancer
5. **Add CI/CD**: Automate builds and deployments

## Support

For issues or questions:
- Check the logs: `docker logs <container-name>`
- Review the docker-compose.yml configuration
- Ensure Docker Desktop has sufficient resources (4GB+ RAM recommended)
