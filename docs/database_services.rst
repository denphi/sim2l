Database Services
=================

Sim2l provides a comprehensive database architecture with four integrated systems for managing simulation data, results, and metadata.

Overview
--------

The database architecture consists of:

1. **Run Database** - Per-run SQLite databases for complete isolation
2. **Cache Service** - Distributed cache with session-based access control
3. **Catalog Service** - Central registry for all sim2l tools and versions
4. **Results Service** - Introspected simulation results with searchable parameters
5. **File Manager** - File and folder management for sim2l runs

Quick Start
-----------

.. code-block:: python

    from sim2l import configure
    from sim2l.database import (
        RunDatabase,
        CacheClient,
        CatalogClient,
        ResultsClient,
        FileManager,
        get_session_manager
    )

    # Configure sim2l with database services
    session = get_session_manager().create_anonymous_session()
    configure(
        use_run_database=True,
        cache_service_url="http://localhost:8001",
        cache_session_id=session.session_id,
        catalog_service_url="http://localhost:8002",
        catalog_session_id=session.session_id,
        results_service_url="http://localhost:8003",
        results_session_id=session.session_id
    )

Run Database
------------

Per-run SQLite databases provide complete isolation for each simulation execution.

Features
^^^^^^^^

- **Complete Run Isolation** - Each execution gets its own database
- **Portable** - Single file contains all run data
- **Rich Schema** - 17 tables for inputs, outputs, logs, metrics, provenance
- **Fast Access** - Local SQLite for high performance

Usage
^^^^^

.. code-block:: python

    from sim2l.database import RunDatabase

    # Open a run database
    run_db = RunDatabase("exec-2024-001")

    # Get run summary
    summary = run_db.get_summary()
    print(f"Simulation: {summary['simulation_name']}")
    print(f"Status: {summary['status']}")
    print(f"Duration: {summary['duration_seconds']}s")

    # Get inputs and outputs
    inputs = run_db.get_inputs()
    outputs = run_db.get_outputs()

    # Get logs
    logs = run_db.get_logs(level='ERROR')

    # Get artifacts (files)
    artifacts = run_db.get_artifacts()

    # Get metrics
    metrics = run_db.get_metrics(category='performance')

Context Manager
^^^^^^^^^^^^^^^

.. code-block:: python

    with RunDatabase("exec-2024-001") as run_db:
        run_db.initialize_run("thermal_sim", "1.0.0")
        run_db.save_input("temperature", 350, "number", units="kelvin")
        run_db.save_output("max_stress", 1.5e8, "number", units="pascal")
        run_db.complete_run("completed", duration_seconds=42.5)

Database Location
^^^^^^^^^^^^^^^^^

Run databases are stored at:

- Default: ``~/.sim2l/runs/{execution_id}.db``
- Configurable via ``SIM2L_RUN_DB_BASE_PATH`` environment variable
- Custom path via ``configure(run_db_base_path="/custom/path")``

API Reference
^^^^^^^^^^^^^

.. autoclass:: sim2l.database.RunDatabase
   :members:
   :undoc-members:
   :show-inheritance:

Cache Service
-------------

Distributed cache service for sharing simulation results across users and machines.

Features
^^^^^^^^

- **Distributed Caching** - Share results across team
- **Session-Based Auth** - Role-based access control
- **TTL Support** - Automatic expiration
- **Invalidation** - Pattern-based cache clearing
- **Statistics** - Hit rates and usage metrics
- **Dual Backend** - SQLite (dev) or PostgreSQL (prod)

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

    # Docker
    docker-compose up cache-service

Using the Client
^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l.database import CacheClient, get_session_manager

    # Create session
    session = get_session_manager().create_anonymous_session()

    # Initialize client
    cache = CacheClient(
        "http://localhost:8001",
        session_id=session.session_id
    )

    # Store in cache
    cache.set(
        cache_key="thermal_sim/350K/result",
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
    result = cache.get("thermal_sim/350K/result")
    if result:
        print(f"Cache hit! Run DB: {result['run_db_path']}")
    else:
        print("Cache miss")

    # Invalidate cache
    cache.invalidate(simulation_id=42, reason="new version")

    # Get statistics
    stats = cache.get_stats(simulation_id=42)
    print(f"Hit rate: {stats['hit_rate']}")

API Endpoints
^^^^^^^^^^^^^

- ``GET /cache/{cache_key}`` - Retrieve cached result
- ``POST /cache`` - Store cache entry
- ``POST /cache/invalidate`` - Invalidate entries
- ``GET /cache/stats`` - Get statistics
- ``GET /health`` - Health check

API Reference
^^^^^^^^^^^^^

.. autoclass:: sim2l.database.CacheClient
   :members:
   :undoc-members:
   :show-inheritance:

Catalog Service
---------------

Central registry for all sim2l tools, versions, and executions.

Features
^^^^^^^^

- **Tool Registry** - All simulations and versions
- **Search** - Find tools by name, tags, metadata
- **Auto-Sync** - Automatically register new installations
- **Execution Tracking** - Record all runs
- **Statistics** - Usage analytics
- **Access Control** - Privilege-based updates

Starting the Service
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # SQLite backend
    python -m sim2l.services.catalog_service --backend sqlite --port 8002

    # PostgreSQL backend
    python -m sim2l.services.catalog_service \
        --backend postgresql \
        --db-url "postgresql://user:pass@localhost/sim2l_catalog" \
        --port 8002

Using the Client
^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l.database import CatalogClient, get_session_manager

    session = get_session_manager().create_anonymous_session(
        privileges=['developer']  # Needed for registration
    )

    catalog = CatalogClient(
        "http://localhost:8002",
        session_id=session.session_id
    )

    # Register a simulation
    catalog.register_simulation(
        name="thermal_sim",
        version="1.0.0",
        description="Thermal stress analysis",
        tags=["thermal", "physics"],
        schema={
            "inputs": {"temperature": {"type": "number", "units": "kelvin"}},
            "outputs": {"max_stress": {"type": "number", "units": "pascal"}}
        }
    )

    # Search for simulations
    results = catalog.search(query="thermal", tags=["physics"])
    for sim in results:
        print(f"{sim['name']} v{sim['version']}: {sim['description']}")

    # Get simulation info
    sim = catalog.get_simulation("thermal_sim", "1.0.0")
    print(f"Schema: {sim['schema']}")

    # Record execution
    catalog.record_execution(
        simulation_id=sim['id'],
        execution_id="exec-001",
        status="completed",
        duration_seconds=42.5
    )

    # Get statistics
    stats = catalog.get_simulation_stats(sim['id'])
    print(f"Total executions: {stats['total_executions']}")
    print(f"Success rate: {stats['success_rate']}")

Auto-Sync
^^^^^^^^^

Automatically register installed simulations:

.. code-block:: python

    from sim2l import configure

    configure(
        catalog_service_url="http://localhost:8002",
        catalog_session_id=session.session_id,
        catalog_auto_sync=True  # Enable auto-sync
    )

    # New simulations are automatically registered when used

API Reference
^^^^^^^^^^^^^

.. autoclass:: sim2l.database.CatalogClient
   :members:
   :undoc-members:
   :show-inheritance:

Results Service
---------------

Introspects simulation results and stores them in a searchable database. Modern replacement for ``registerSquidpgSimtool``.

Features
^^^^^^^^

- **Automatic Introspection** - Extracts parameter schemas
- **Searchable Storage** - Query by parameter values
- **Parameter Statistics** - Min, max, average across runs
- **Type-Aware** - Understands parameter types
- **REST API** - Programmatic access
- **Dual Backend** - SQLite or PostgreSQL

Starting the Service
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # SQLite backend
    python -m sim2l.services.results_service --backend sqlite --port 8003

    # PostgreSQL backend
    python -m sim2l.services.results_service \
        --backend postgresql \
        --db-url "postgresql://user:pass@localhost/sim2l_results" \
        --port 8003

Using the Client
^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l.database import ResultsClient, get_session_manager

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    # Register a result (introspects run database automatically)
    result = client.register_result("exec-2024-001")
    print(f"Registered as result ID: {result['result_id']}")

    # Search by parameter values
    results = client.search(
        simulation_name="thermal_sim",
        input_filters={'temperature': 350},
        output_filters={'max_stress': 1.5e8}
    )

    for result in results:
        print(f"Execution: {result['execution_id']}")
        print(f"  Inputs: {result['input_params']}")
        print(f"  Outputs: {result['output_params']}")

    # Get parameter statistics
    stats = client.get_parameter_stats(
        "thermal_sim",
        "max_stress",
        param_class="output"
    )

    print(f"Average max_stress: {stats['avg_value']}")
    print(f"Range: {stats['min_value']} - {stats['max_value']}")
    print(f"Analyzed {stats['count']} runs")

What Gets Introspected
^^^^^^^^^^^^^^^^^^^^^^

The Results Service automatically extracts from each run:

- **Parameter Schemas** - Types, units, min/max, defaults
- **Input Values** - Actual input parameter values
- **Output Values** - Computed output values
- **Metadata** - Simulation name, version, status, duration

API Reference
^^^^^^^^^^^^^

.. autoclass:: sim2l.database.ResultsClient
   :members:
   :undoc-members:
   :show-inheritance:

File Manager
------------

Manage files generated by sim2l runs.

Features
^^^^^^^^

- **File Retrieval** - Get files from run databases
- **Export** - Export files to filesystem
- **Organization** - Folder hierarchies
- **Metadata** - Rich file information
- **Batch Operations** - Process multiple files

Usage
^^^^^

.. code-block:: python

    from sim2l.database import FileManager

    fm = FileManager()

    # Get all files from a run
    files = fm.get_run_files("exec-2024-001")
    for file in files:
        print(f"{file['name']}: {file['size']} bytes")
        print(f"  Category: {file['category']}")
        print(f"  Type: {file['content_type']}")

    # Export a file
    success = fm.export_run_file(
        "exec-2024-001",
        "output.dat",
        "/tmp/output.dat"
    )

    # Get all files for a simulation
    files = fm.get_simulation_files("thermal_sim", "1.0.0")

    # Batch export
    import os
    output_dir = "/tmp/exports"
    os.makedirs(output_dir, exist_ok=True)

    for file in files:
        output_path = os.path.join(output_dir, file['name'])
        fm.export_run_file(file['execution_id'], file['name'], output_path)

Organizing Files
^^^^^^^^^^^^^^^^

.. code-block:: python

    # Create folder
    folder = fm.create_folder(
        name="simulation_outputs",
        creator="user123"
    )

    # Create file entry
    fm.create_file(
        name="result.csv",
        size=2048,
        uri="/data/result.csv",
        creator="user123",
        parent_id=folder['id']
    )

    # List folder contents
    contents = fm.list_folder(folder['id'])
    for item in contents:
        print(item['name'])

API Reference
^^^^^^^^^^^^^

.. autoclass:: sim2l.database.FileManager
   :members:
   :undoc-members:
   :show-inheritance:

Session Management
------------------

Authentication and privilege checking for all services.

Features
^^^^^^^^

- **User Management** - Create users with roles
- **Session Tokens** - JWT-like session IDs
- **Role-Based Access** - User, developer, admin privileges
- **Anonymous Sessions** - Temporary access
- **TTL Support** - Session expiration

Usage
^^^^^

.. code-block:: python

    from sim2l.database import get_session_manager

    # Get global session manager
    manager = get_session_manager()

    # Create user
    manager.create_user(
        username="alice",
        password="secret",
        role="developer",
        email="alice@example.com"
    )

    # Authenticate
    session = manager.authenticate("alice", "secret")
    print(f"Session ID: {session.session_id}")
    print(f"Role: {session.role}")

    # Check privileges
    has_privilege = manager.check_privilege(
        session.session_id,
        "register_simulation"
    )

    # Create anonymous session
    anon_session = manager.create_anonymous_session(
        privileges=['read_cache'],
        ttl_hours=1
    )

    # Use session with services
    cache = CacheClient(
        "http://localhost:8001",
        session_id=session.session_id
    )

Roles and Privileges
^^^^^^^^^^^^^^^^^^^^

**User Role**:

- Read cache
- Read catalog
- Execute simulations

**Developer Role**:

- All user privileges
- Register simulations
- Update catalog
- Invalidate cache

**Admin Role**:

- All developer privileges
- User management
- Service administration

API Reference
^^^^^^^^^^^^^

.. autoclass:: sim2l.database.SessionManager
   :members:
   :undoc-members:
   :show-inheritance:

.. autofunction:: sim2l.database.get_session_manager

Deployment
----------

Local Development
^^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l import configure

    # Use local databases only
    configure(use_run_database=True)

    # Run simulation
    result = sim.run(temperature=350)

Docker Deployment
^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Start all services with PostgreSQL
    cd docker
    docker-compose --profile prod up -d

    # Services available at:
    # - Cache: http://localhost:8001
    # - Catalog: http://localhost:8002
    # - Results: http://localhost:8003

Hybrid Deployment
^^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l import configure
    from sim2l.database import get_session_manager

    # Run databases locally, services remote
    session = get_session_manager().create_anonymous_session()

    configure(
        use_run_database=True,  # Local
        cache_service_url="http://cache-server:8001",  # Remote
        cache_session_id=session.session_id,
        catalog_service_url="http://catalog-server:8002",  # Remote
        catalog_session_id=session.session_id
    )

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

All services support environment variable configuration:

.. code-block:: bash

    # Run Database
    export SIM2L_USE_RUN_DATABASE=true
    export SIM2L_RUN_DB_BASE_PATH=$HOME/.sim2l/runs

    # Cache Service
    export SIM2L_CACHE_SERVICE_URL=http://localhost:8001
    export SIM2L_CACHE_SESSION_ID=session-id-here

    # Catalog Service
    export SIM2L_CATALOG_SERVICE_URL=http://localhost:8002
    export SIM2L_CATALOG_SESSION_ID=session-id-here
    export SIM2L_CATALOG_AUTO_SYNC=true

    # Results Service
    export SIM2L_RESULTS_SERVICE_URL=http://localhost:8003
    export SIM2L_RESULTS_SESSION_ID=session-id-here

Performance
-----------

Benchmarks
^^^^^^^^^^

================= =================== ====================
Component         Metric              Value
================= =================== ====================
Run Database      Write speed         ~10,000 inserts/sec
Run Database      Typical size        1-10 MB
Cache Service     Latency (local)     <10ms
Cache Service     Throughput (SQLite) ~1,000 req/sec
Cache Service     Throughput (PG)     ~10,000 req/sec
Catalog Service   Search speed        <100ms
Results Service   Introspection       <1s per run
================= =================== ====================

Best Practices
^^^^^^^^^^^^^^

1. **Use Run Databases** - Always enable for complete tracking
2. **Cache Strategically** - Cache expensive computations
3. **Register Results** - Make simulations discoverable
4. **Auto-Sync Catalog** - Keep catalog up-to-date
5. **Export Important Files** - Don't rely on run DBs forever

Troubleshooting
---------------

Service Won't Start
^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Check port availability
    lsof -i :8001

    # Test database connectivity
    psql -h localhost -U user -d sim2l_cache

    # View service logs
    python -m sim2l.services.cache_service --backend sqlite 2>&1 | tee cache.log

Can't Connect to Service
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # Check service health
    import requests
    response = requests.get("http://localhost:8001/health")
    print(response.json())

    # Verify session
    from sim2l.database import get_session_manager
    manager = get_session_manager()
    session = manager.get_session(session_id)
    if session and session.is_valid():
        print("Session is valid")
    else:
        print("Session is invalid or expired")

Run Database Not Found
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import os
    from sim2l.database import RunDatabase

    # Check if database exists
    db_path = os.path.expanduser(f"~/.sim2l/runs/{execution_id}.db")
    if os.path.exists(db_path):
        print(f"Database exists: {db_path}")
    else:
        print(f"Database not found: {db_path}")

    # Try to open
    try:
        run_db = RunDatabase(execution_id)
        print("Successfully opened run database")
    except Exception as e:
        print(f"Error: {e}")

See Also
--------

- :doc:`quickstart` - Getting started guide
- :doc:`api_reference` - Complete API documentation
- :doc:`examples` - Code examples
- GitHub: Database Architecture Documentation
