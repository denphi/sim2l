Catalog Service
===============

Central registry for all sim2l tools, versions, and executions.

Quick Start
-----------

.. code-block:: bash

    # Start service
    python -m sim2l.services.catalog_service --backend sqlite --port 8002

.. code-block:: python

    from sim2l.database import CatalogClient, get_session_manager

    session = get_session_manager().create_anonymous_session(privileges=['developer'])
    catalog = CatalogClient("http://localhost:8002", session_id=session.session_id)

    # Register simulation
    catalog.register_simulation(
        name="thermal_sim",
        version="1.0.0",
        description="Thermal stress analysis",
        tags=["thermal", "physics"],
        schema={"inputs": {...}, "outputs": {...}}
    )

    # Search
    results = catalog.search(query="thermal", tags=["physics"])

    # Get statistics
    stats = catalog.get_simulation_stats(simulation_id)

REST API
--------

- ``GET /simulations/search`` - Search simulations
- ``GET /simulations/{name}`` - Get simulation info
- ``POST /simulations`` - Register simulation
- ``POST /executions`` - Record execution
- ``GET /simulations/{id}/stats`` - Get statistics
- ``GET /health`` - Health check

API Reference
-------------

.. autoclass:: sim2l.database.CatalogClient
   :members:
