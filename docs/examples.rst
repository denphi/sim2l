Examples
========

Code examples for common sim2l tasks.

Basic Simulation
----------------

.. code-block:: python

    import sim2l

    sim = sim2l.load("thermal_sim")
    result = sim.run(temperature=350, pressure=101325)
    print(result.outputs)

With Run Database
-----------------

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import RunDatabase

    configure(use_run_database=True)

    sim = load("thermal_sim")
    result = sim.run(temperature=350)

    run_db = RunDatabase(result.execution_id)
    summary = run_db.get_summary()
    print(f"Duration: {summary['duration_seconds']}s")

With Caching
------------

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import get_session_manager

    session = get_session_manager().create_anonymous_session()
    configure(
        use_run_database=True,
        cache_service_url="http://localhost:8001",
        cache_session_id=session.session_id
    )

    sim = load("thermal_sim")

    # First run - cache miss
    result1 = sim.run(temperature=350)

    # Second run - cache hit
    result2 = sim.run(temperature=350)

File Export
-----------

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import FileManager

    configure(use_run_database=True)
    sim = load("thermal_sim")
    result = sim.run(temperature=350)

    fm = FileManager()
    files = fm.get_run_files(result.execution_id)

    for file in files:
        fm.export_run_file(result.execution_id, file['name'], f"/tmp/{file['name']}")

Result Search
-------------

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import ResultsClient, get_session_manager

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient("http://localhost:8003", session_id=session.session_id)

    # Run simulations
    configure(use_run_database=True)
    sim = load("thermal_sim")

    for temp in [300, 325, 350, 375, 400]:
        result = sim.run(temperature=temp)
        client.register_result(result.execution_id)

    # Search
    results = client.search(
        simulation_name="thermal_sim",
        input_filters={'temperature': 350}
    )

    # Statistics
    stats = client.get_parameter_stats("thermal_sim", "max_stress")
    print(f"Average: {stats['avg_value']}")

Complete Example
----------------

.. code-block:: python

    from sim2l import configure, load
    from sim2l.database import (
        get_session_manager,
        RunDatabase,
        CacheClient,
        ResultsClient,
        FileManager
    )

    # Setup
    session = get_session_manager().create_anonymous_session()
    configure(
        use_run_database=True,
        cache_service_url="http://localhost:8001",
        cache_session_id=session.session_id
    )

    # Run simulation
    sim = load("thermal_sim")
    result = sim.run(temperature=350)

    # Access run database
    run_db = RunDatabase(result.execution_id)
    print(run_db.get_summary())

    # Register result
    results_client = ResultsClient("http://localhost:8003", session_id=session.session_id)
    results_client.register_result(result.execution_id)

    # Export files
    fm = FileManager()
    files = fm.get_run_files(result.execution_id)
    for file in files:
        fm.export_run_file(result.execution_id, file['name'], f"/data/{file['name']}")

More Examples
-------------

See the ``examples/`` directory in the repository:

- ``file_manager_usage.py`` - FileManager examples
- ``results_service_usage.py`` - Results Service examples
- Additional workflow examples
