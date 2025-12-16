Cache Service
=============

The Cache Service provides distributed caching for simulation results with session-based access control.

Overview
--------

Features:

- **Distributed Caching** - Share results across team members
- **Session Authentication** - Role-based access control
- **TTL Support** - Automatic cache expiration
- **Invalidation** - Pattern-based cache clearing
- **Statistics** - Hit rates and usage metrics
- **Dual Backend** - SQLite (dev) or PostgreSQL (prod)

Quick Start
-----------

Starting the Service
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # SQLite backend (development)
    python -m sim2l.services.cache_service --backend sqlite --port 8001

    # PostgreSQL backend (production)
    python -m sim2l.services.cache_service \
        --backend postgresql \
        --db-url "postgresql://user:pass@localhost/sim2l_cache" \
        --port 8001

Using the Client
^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l.database import CacheClient, get_session_manager

    # Create session
    session = get_session_manager().create_anonymous_session()

    # Connect to service
    cache = CacheClient(
        "http://localhost:8001",
        session_id=session.session_id
    )

    # Store in cache
    cache.set(
        cache_key="thermal_sim/350K",
        simulation_id=42,
        simulation_name="thermal_sim",
        simulation_version="1.0.0",
        execution_id="exec-001",
        squid_id="thermal_sim/1.0.0/xyz",
        input_hash="hash123",
        run_db_path="/path/to/run.db",
        ttl_hours=24
    )

    # Retrieve from cache
    result = cache.get("thermal_sim/350K")
    if result:
        print("Cache hit!")
    else:
        print("Cache miss")

REST API
--------

GET /cache/{cache_key}
^^^^^^^^^^^^^^^^^^^^^^

Retrieve a cached result.

**Headers**:
- ``X-Session-ID``: Session ID for authentication

**Response**:

.. code-block:: json

    {
      "cache_key": "thermal_sim/350K",
      "simulation_id": 42,
      "simulation_name": "thermal_sim",
      "simulation_version": "1.0.0",
      "execution_id": "exec-001",
      "squid_id": "thermal_sim/1.0.0/xyz",
      "input_hash": "hash123",
      "run_db_path": "/path/to/run.db",
      "created_at": "2024-01-01T12:00:00",
      "expires_at": "2024-01-02T12:00:00",
      "hit_count": 5
    }

POST /cache
^^^^^^^^^^^

Store a cache entry.

**Request**:

.. code-block:: json

    {
      "cache_key": "thermal_sim/350K",
      "simulation_id": 42,
      "simulation_name": "thermal_sim",
      "simulation_version": "1.0.0",
      "execution_id": "exec-001",
      "squid_id": "thermal_sim/1.0.0/xyz",
      "input_hash": "hash123",
      "run_db_path": "/path/to/run.db",
      "ttl_hours": 24,
      "metadata": {}
    }

**Response**:

.. code-block:: json

    {
      "success": true,
      "cache_key": "thermal_sim/350K"
    }

POST /cache/invalidate
^^^^^^^^^^^^^^^^^^^^^^

Invalidate cache entries.

**Request**:

.. code-block:: json

    {
      "simulation_id": 42,
      "pattern": "thermal_sim/*",
      "reason": "new version released"
    }

**Response**:

.. code-block:: json

    {
      "success": true,
      "invalidated_count": 15
    }

GET /cache/stats
^^^^^^^^^^^^^^^^

Get cache statistics.

**Query Parameters**:
- ``simulation_id``: Filter by simulation (optional)

**Response**:

.. code-block:: json

    {
      "total_entries": 1000,
      "total_hits": 5000,
      "total_misses": 500,
      "hit_rate": 0.909,
      "total_size_bytes": 104857600,
      "invalidation_count": 10
    }

GET /health
^^^^^^^^^^^

Health check.

**Response**:

.. code-block:: json

    {
      "status": "healthy",
      "service": "cache",
      "backend": "postgresql"
    }

Configuration
-------------

Command Line
^^^^^^^^^^^^

.. code-block:: bash

    python -m sim2l.services.cache_service \
        --backend {sqlite|postgresql} \
        --db-path /path/to/cache.db \
        --db-url postgresql://user:pass@host/db \
        --port 8001 \
        --host 0.0.0.0 \
        --no-auth

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    export SIM2L_CACHE_BACKEND=postgresql
    export SIM2L_CACHE_DB_URL=postgresql://user:pass@localhost/sim2l_cache
    export SIM2L_CACHE_PORT=8001

Docker
^^^^^^

.. code-block:: yaml

    services:
      cache-service:
        build:
          context: .
          dockerfile: docker/Dockerfile.cache
        ports:
          - "8001:8001"
        environment:
          - CACHE_BACKEND=postgresql
          - CACHE_DB_URL=postgresql://user:pass@postgres/sim2l_cache

API Reference
-------------

.. autoclass:: sim2l.database.CacheClient
   :members:
   :undoc-members:
   :show-inheritance:
