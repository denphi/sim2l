Results Service
===============

MCP Access
----------

sim2l owns the MCP server because it exposes sim2l capabilities to agents.
ARC should consume these tools as an MCP client rather than exposing ARC
workflow controls from sim2l.

Install the optional dependency and start the MCP server with::

   pip install "sim2l[mcp]"
   sim2l mcp serve --transport stdio

The server exposes tool calls for logging in to sim2l services, searching the
catalog, running registered simulations, and listing/searching results. Login
exchanges username/password for per-service tokens held by the MCP server
process; later tool calls forward those tokens to the existing REST services.

Introspects simulation results and stores them in a searchable database. Modern replacement for ``registerSquidpgSimtool``.

Quick Start
-----------

.. code-block:: bash

    # Start service
    python -m sim2l.services.results_service --backend sqlite --port 8003

.. code-block:: python

    from sim2l.database import ResultsClient, get_session_manager

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient("http://localhost:8003", session_id=session.session_id)

    # Register result (introspects automatically)
    client.register_result("exec-2024-001")

    # Search by parameters
    results = client.search(
        simulation_name="thermal_sim",
        input_filters={'temperature': 350},
        output_filters={'max_stress': 1.5e8}
    )

    # Get statistics
    stats = client.get_parameter_stats("thermal_sim", "max_stress", param_class="output")

What Gets Introspected
----------------------

From each run database:

- **Parameter Schemas** - Types, units, min/max, defaults
- **Input Values** - Actual input parameter values
- **Output Values** - Computed output values
- **Metadata** - Simulation name, version, status, duration

REST API
--------

- ``POST /register`` - Register a result
- ``POST /search`` - Search by parameters
- ``GET /results/{execution_id}`` - Get specific result
- ``GET /stats/{simulation_name}/{param_name}`` - Get parameter statistics
- ``GET /health`` - Health check

API Reference
-------------

.. autoclass:: sim2l.database.ResultsClient
   :members:
