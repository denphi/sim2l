Deployment Guide
================

Production deployment of sim2l services.

Architecture
------------

Three deployment modes:

1. **Local Only** - Run databases only, no services
2. **Docker** - All services in containers
3. **Hybrid** - Local run databases + remote services

Local Deployment
----------------

Development setup with no services:

.. code-block:: python

    from sim2l import configure

    configure(use_run_database=True)

    # Run databases stored in ~/.sim2l/runs/

Docker Deployment
-----------------

Full production stack with Docker Compose.

Setup
^^^^^

.. code-block:: bash

    cd docker
    docker-compose --profile prod up -d

Services:

- **PostgreSQL**: Port 5432
- **Cache Service**: Port 8001
- **Catalog Service**: Port 8002
- **Results Service**: Port 8003

Environment
^^^^^^^^^^^

.. code-block:: bash

    # PostgreSQL
    POSTGRES_USER=sim2l
    POSTGRES_PASSWORD=secret
    POSTGRES_DB=sim2l

    # Cache Service
    CACHE_BACKEND=postgresql
    CACHE_DB_URL=postgresql://sim2l:secret@postgres/sim2l_cache

    # Catalog Service
    CATALOG_BACKEND=postgresql
    CATALOG_DB_URL=postgresql://sim2l:secret@postgres/sim2l_catalog

    # Results Service
    RESULTS_BACKEND=postgresql
    RESULTS_DB_URL=postgresql://sim2l:secret@postgres/sim2l_results

Hybrid Deployment
-----------------

Local run databases with remote services.

.. code-block:: python

    from sim2l import configure
    from sim2l.database import get_session_manager

    session = get_session_manager().create_anonymous_session()

    configure(
        use_run_database=True,  # Local
        cache_service_url="http://cache.example.com:8001",  # Remote
        cache_session_id=session.session_id,
        catalog_service_url="http://catalog.example.com:8002",  # Remote
        catalog_session_id=session.session_id,
        results_service_url="http://results.example.com:8003"  # Remote
    )

Production Checklist
--------------------

Infrastructure
^^^^^^^^^^^^^^

- [ ] PostgreSQL database server
- [ ] Docker host or Kubernetes cluster
- [ ] Load balancer (optional)
- [ ] Monitoring (Prometheus/Grafana)
- [ ] Logging (ELK stack)

Security
^^^^^^^^

- [ ] Enable authentication
- [ ] Configure TLS/SSL
- [ ] Set strong passwords
- [ ] Network isolation
- [ ] Regular backups

Performance
^^^^^^^^^^^

- [ ] PostgreSQL tuning
- [ ] Connection pooling
- [ ] Cache size limits
- [ ] TTL configuration
- [ ] Index optimization

Monitoring
^^^^^^^^^^

- [ ] Service health checks
- [ ] Database metrics
- [ ] Cache hit rates
- [ ] Error logging
- [ ] Performance metrics

Scaling
-------

Horizontal Scaling
^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

    services:
      cache-service:
        deploy:
          replicas: 3
        environment:
          - CACHE_BACKEND=postgresql

      catalog-service:
        deploy:
          replicas: 2

Load Balancing
^^^^^^^^^^^^^^

Use nginx or HAProxy:

.. code-block:: nginx

    upstream cache {
        server cache1:8001;
        server cache2:8001;
        server cache3:8001;
    }

    server {
        listen 80;
        location / {
            proxy_pass http://cache;
        }
    }

Maintenance
-----------

Backups
^^^^^^^

.. code-block:: bash

    # PostgreSQL backup
    pg_dump -h localhost -U sim2l sim2l_cache > cache_backup.sql

    # Run databases
    tar -czf runs_backup.tar.gz ~/.sim2l/runs/

Updates
^^^^^^^

.. code-block:: bash

    # Pull latest images
    docker-compose pull

    # Restart services
    docker-compose --profile prod up -d

Troubleshooting
^^^^^^^^^^^^^^^

.. code-block:: bash

    # View logs
    docker-compose logs -f cache-service

    # Check service health
    curl http://localhost:8001/health

    # Database connection
    docker-compose exec postgres psql -U sim2l -d sim2l_cache
