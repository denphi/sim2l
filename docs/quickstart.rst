Quick Start Guide
=================

This guide will help you get started with sim2l in 5 minutes.

Installation
------------

.. code-block:: bash

    pip install sim2l

Basic Usage
-----------

Minimal Example
^^^^^^^^^^^^^^^

.. code-block:: python

    import sim2l

    # Load a simulation tool
    sim = sim2l.load("thermal_sim")

    # Run the simulation
    result = sim.run(temperature=350, pressure=101325)

    # Access results
    print(result.outputs)

With Run Database
^^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l import configure, load

    # Enable run database
    configure(use_run_database=True)

    # Run simulation
    sim = load("thermal_sim")
    result = sim.run(temperature=350)

    # Access run database
    from sim2l.database import RunDatabase
    run_db = RunDatabase(result.execution_id)

    # Get run information
    summary = run_db.get_summary()
    print(f"Status: {summary['status']}")
    print(f"Duration: {summary['duration_seconds']}s")

    # Get all outputs
    outputs = run_db.get_outputs()
    for output in outputs:
        print(f"{output['name']}: {output['value']}")

With Services
^^^^^^^^^^^^^

Start the services:

.. code-block:: bash

    # Terminal 1: Cache service
    python -m sim2l.services.cache_service --port 8001

    # Terminal 2: Catalog service
    python -m sim2l.services.catalog_service --port 8002

    # Terminal 3: Results service
    python -m sim2l.services.results_service --port 8003

Use in your code:

.. code-block:: python

    from sim2l import configure
    from sim2l.database import get_session_manager

    # Create session
    session = get_session_manager().create_anonymous_session()

    # Configure with all services
    configure(
        use_run_database=True,
        cache_service_url="http://localhost:8001",
        cache_session_id=session.session_id,
        catalog_service_url="http://localhost:8002",
        catalog_session_id=session.session_id,
        catalog_auto_sync=True
    )

    # Run simulation (uses cache and catalog automatically)
    sim = sim2l.load("thermal_sim")
    result = sim.run(temperature=350)

    # Register result for searchability
    from sim2l.database import ResultsClient
    results = ResultsClient("http://localhost:8003", session_id=session.session_id)
    results.register_result(result.execution_id)

Docker Quick Start
------------------

.. code-block:: bash

    # Clone repository
    git clone https://github.com/yourusername/sim2l.git
    cd sim2l

    # Start all services
    docker-compose up -d

    # Services available at:
    # - Cache: http://localhost:8001
    # - Catalog: http://localhost:8002
    # - Results: http://localhost:8003

Common Workflows
----------------

Workflow 1: Simple Simulation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import sim2l

    # Load and run
    sim = sim2l.load("thermal_sim")
    result = sim.run(temperature=350, pressure=101325)

    # Check results
    print(result.outputs['max_stress'])

Workflow 2: With Caching
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import get_session_manager

    # Setup
    session = get_session_manager().create_anonymous_session()
    configure(
        use_run_database=True,
        cache_service_url="http://localhost:8001",
        cache_session_id=session.session_id
    )

    # First run (cache miss)
    sim = load("thermal_sim")
    result1 = sim.run(temperature=350)
    print("First run completed")

    # Second run (cache hit - much faster!)
    result2 = sim.run(temperature=350)
    print("Second run completed (from cache)")

Workflow 3: File Management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import FileManager

    # Run simulation
    configure(use_run_database=True)
    sim = load("thermal_sim")
    result = sim.run(temperature=350)

    # Get generated files
    fm = FileManager()
    files = fm.get_run_files(result.execution_id)

    # Export files
    for file in files:
        fm.export_run_file(
            result.execution_id,
            file['name'],
            f"/tmp/{file['name']}"
        )
        print(f"Exported: {file['name']}")

Workflow 4: Result Search
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from sim2l import configure
    from sim2l.database import ResultsClient, get_session_manager

    # Setup
    session = get_session_manager().create_anonymous_session()
    client = ResultsClient("http://localhost:8003", session_id=session.session_id)

    # Run and register
    configure(use_run_database=True)
    sim = sim2l.load("thermal_sim")

    # Run multiple simulations
    for temp in [300, 325, 350, 375, 400]:
        result = sim.run(temperature=temp)
        client.register_result(result.execution_id)
        print(f"Registered run at {temp}K")

    # Search for results
    results = client.search(
        simulation_name="thermal_sim",
        input_filters={'temperature': 350}
    )
    print(f"Found {len(results)} runs at 350K")

    # Get statistics
    stats = client.get_parameter_stats(
        "thermal_sim",
        "max_stress",
        param_class="output"
    )
    print(f"Average max_stress: {stats['avg_value']}")

Next Steps
----------

- Read the :doc:`database_services` documentation for detailed information
- Explore :doc:`examples` for more code samples
- Check the :doc:`api_reference` for complete API documentation
- See :doc:`deployment` for production setup

Configuration Options
---------------------

Environment Variables
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Run Database
    export SIM2L_USE_RUN_DATABASE=true
    export SIM2L_RUN_DB_BASE_PATH=$HOME/.sim2l/runs

    # Cache Service
    export SIM2L_CACHE_SERVICE_URL=http://localhost:8001
    export SIM2L_CACHE_SESSION_ID=<session-id>

    # Catalog Service
    export SIM2L_CATALOG_SERVICE_URL=http://localhost:8002
    export SIM2L_CATALOG_SESSION_ID=<session-id>
    export SIM2L_CATALOG_AUTO_SYNC=true

    # Results Service
    export SIM2L_RESULTS_SERVICE_URL=http://localhost:8003
    export SIM2L_RESULTS_SESSION_ID=<session-id>

Config File
^^^^^^^^^^^

Create ``~/.sim2l/config.yaml``:

.. code-block:: yaml

    use_run_database: true
    run_db_base_path: ~/.sim2l/runs

    cache_service_url: http://localhost:8001
    catalog_service_url: http://localhost:8002
    catalog_auto_sync: true

    results_service_url: http://localhost:8003

Programmatic
^^^^^^^^^^^^

.. code-block:: python

    from sim2l import configure

    configure(
        use_run_database=True,
        run_db_base_path="~/.sim2l/runs",
        cache_service_url="http://localhost:8001",
        cache_session_id=session.session_id,
        catalog_service_url="http://localhost:8002",
        catalog_session_id=session.session_id,
        catalog_auto_sync=True,
        results_service_url="http://localhost:8003",
        results_session_id=session.session_id
    )

Troubleshooting
---------------

Import Errors
^^^^^^^^^^^^^

.. code-block:: python

    # If you get ImportError
    import sys
    print(sys.path)

    # Make sure sim2l is installed
    pip install -e .

Service Connection Errors
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # Test service health
    import requests

    try:
        response = requests.get("http://localhost:8001/health")
        print(f"Cache service: {response.json()}")
    except Exception as e:
        print(f"Cache service not available: {e}")

Run Database Not Found
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import os
    from pathlib import Path

    # Check database location
    db_path = Path.home() / ".sim2l" / "runs" / f"{execution_id}.db"
    if db_path.exists():
        print(f"Database exists: {db_path}")
    else:
        print(f"Database not found: {db_path}")
        print("Make sure use_run_database=True was set before running")

Getting Help
------------

- Documentation: https://sim2l.readthedocs.io
- GitHub Issues: https://github.com/yourusername/sim2l/issues
- Examples: See the ``examples/`` directory in the repository
