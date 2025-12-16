Migration Guide
===============

Migrating from legacy simtool/papers to sim2l.

Overview
--------

Key changes:

- **Run databases** replace individual file storage
- **Cache service** replaces direct PostgreSQL access
- **Results service** replaces registerSquidpgSimtool script
- **Catalog service** provides tool discovery
- **FileManager** replaces file model classes

From Simtool to Sim2l
---------------------

Old Code
^^^^^^^^

.. code-block:: python

    import simtool

    sim = simtool.load("thermal_sim")
    result = sim.run(temperature=350)

New Code
^^^^^^^^

.. code-block:: python

    import sim2l

    sim = sim2l.load("thermal_sim")
    result = sim.run(temperature=350)

    # Now with run database
    from sim2l.database import RunDatabase
    run_db = RunDatabase(result.execution_id)

From registerSquidpgSimtool
----------------------------

Old Way
^^^^^^^

.. code-block:: bash

    registerSquidpgSimtool -s "thermal_sim/r1/squid-123"

New Way
^^^^^^^

.. code-block:: python

    from sim2l.database import ResultsClient, get_session_manager

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient("http://localhost:8003", session_id=session.session_id)

    client.register_result(
        execution_id="exec-123",
        squid_id="thermal_sim/r1/squid-123"
    )

From File Models
----------------

Old Way
^^^^^^^

.. code-block:: python

    from api.models.file import File

    file = File.create(
        name='output.dat',
        size=1024,
        uri='/path/to/file',
        creator='user123'
    )

New Way
^^^^^^^

.. code-block:: python

    from sim2l.database import FileManager

    fm = FileManager()

    # Get files from run
    files = fm.get_run_files("exec-2024-001")

    # Export files
    fm.export_run_file("exec-2024-001", "output.dat", "/tmp/output.dat")

Migration Steps
---------------

1. **Install sim2l**

   .. code-block:: bash

       pip install sim2l

2. **Enable run databases**

   .. code-block:: python

       from sim2l import configure
       configure(use_run_database=True)

3. **Start services**

   .. code-block:: bash

       python -m sim2l.services.cache_service --port 8001 &
       python -m sim2l.services.catalog_service --port 8002 &
       python -m sim2l.services.results_service --port 8003 &

4. **Update code**

   Replace simtool imports with sim2l:

   .. code-block:: python

       # Old
       import simtool

       # New
       import sim2l

5. **Migrate historical data**

   Register existing runs:

   .. code-block:: python

       from sim2l.database import ResultsClient, get_session_manager

       session = get_session_manager().create_anonymous_session()
       client = ResultsClient("http://localhost:8003", session_id=session.session_id)

       # For each historical run
       for execution_id in historical_runs:
           try:
               client.register_result(execution_id)
           except Exception as e:
               print(f"Failed to register {execution_id}: {e}")

Backward Compatibility
----------------------

Sim2l maintains compatibility with simtool APIs where possible. Most code should work without changes.

Breaking Changes:

- File models removed (use FileManager)
- Direct PostgreSQL access deprecated (use services)
- Cache structure changed (use CacheClient)

See Also
--------

- :doc:`quickstart` - Getting started guide
- :doc:`database_services` - New database architecture
- GitHub: LEGACY_CACHE_MIGRATION.md
