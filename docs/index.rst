Welcome to Sim2l's documentation!
==================================

Sim2l is a modern simulation framework with integrated database services for managing simulation data, results, and metadata.

Contents
========

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   readme
   installation
   quickstart

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   usage
   database_services
   file_management
   examples

.. toctree::
   :maxdepth: 2
   :caption: Services

   services/cache_service
   services/catalog_service
   services/results_service

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   reference
   api/database
   api/services
   api/core

.. toctree::
   :maxdepth: 1
   :caption: Additional Information

   deployment
   contributing
   authors
   history

Features
========

Database Architecture
---------------------

* **Run Database** - Per-run SQLite databases for complete isolation
* **Cache Service** - Distributed cache with session-based access control
* **Catalog Service** - Central registry for all sim2l tools and versions
* **Results Service** - Introspected simulation results with searchable parameters
* **File Manager** - File and folder management for sim2l runs

Key Capabilities
----------------

* **Complete Run Tracking** - Every execution stored in its own database
* **Distributed Caching** - Share results across team members
* **Tool Discovery** - Searchable catalog of all simulations
* **Parameter Search** - Find runs by input/output values
* **File Export** - Easy access to generated files
* **Session-Based Auth** - Secure access to all services

Quick Example
=============

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import get_session_manager

    # Configure with services
    session = get_session_manager().create_anonymous_session()
    configure(
        use_run_database=True,
        cache_service_url="http://localhost:8001",
        cache_session_id=session.session_id
    )

    # Run simulation
    sim = load("thermal_sim")
    result = sim.run(temperature=350)

    # Access run data
    from sim2l.database import RunDatabase
    run_db = RunDatabase(result.execution_id)
    print(run_db.get_summary())

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
