MCP Integration
===============

sim2l includes a Model Context Protocol (MCP) server that exposes registered
simulations and execution results as tools for MCP-compatible clients. The MCP
server is a gateway to the existing sim2l catalog, results, and cache services;
those services must be running before their tools can be used.

Installation
------------

Install sim2l with the optional MCP dependency:

.. code-block:: bash

   pip install "sim2l[mcp]"

The core sim2l package does not require the MCP dependency. If it is missing,
the server reports an installation error when it starts.

Starting the Server
-------------------

Start the sim2l services, then run the MCP server with the standard input/output
transport:

.. code-block:: bash

   sim2l mcp serve --transport stdio

The ``stdio`` transport is intended for a local MCP client that launches the
server as a subprocess. For example, a client configuration can launch:

.. code-block:: json

   {
     "command": "sim2l",
     "args": ["mcp", "serve", "--transport", "stdio"]
   }

The transport name is passed to the installed MCP SDK. Other transports
supported by that SDK can be selected with ``--transport``.

Service Configuration
---------------------

By default, the MCP gateway connects to:

- Cache service: ``http://localhost:8001``
- Catalog service: ``http://localhost:8002``
- Results service: ``http://localhost:8003``

Override the service locations with environment variables:

.. code-block:: bash

   export SIM2L_CACHE_URL=https://sim2l.example.com/cache
   export SIM2L_CATALOG_URL=https://sim2l.example.com/catalog
   export SIM2L_RESULTS_URL=https://sim2l.example.com/results
   sim2l mcp serve --transport stdio

Or pass URLs and the HTTP request timeout directly:

.. code-block:: bash

   sim2l mcp serve \
       --transport stdio \
       --cache-url https://sim2l.example.com/cache \
       --catalog-url https://sim2l.example.com/catalog \
       --results-url https://sim2l.example.com/results \
       --timeout 60

Available Tools
---------------

The server exposes the following MCP tools:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool
     - Purpose
   * - ``sim2l_login``
     - Log in to the catalog, results, and cache services.
   * - ``sim2l_logout``
     - Remove service tokens held by the MCP server process.
   * - ``sim2l_search_simulations``
     - Search registered simulations by text, tags, and status.
   * - ``sim2l_get_simulation``
     - Get catalog metadata for a simulation and optional version.
   * - ``sim2l_run_simulation``
     - Run a registered simulation with an optional version and input parameters.
   * - ``sim2l_search_results``
     - Search results by simulation, version, status, inputs, and outputs.
   * - ``sim2l_list_results``
     - List recent execution results.
   * - ``sim2l_get_result``
     - Get one result by execution ID.

Authentication
--------------

Call ``sim2l_login`` before using services that require authentication. The
gateway submits the username and password independently to the catalog,
results, and cache services. It stores successful service tokens in the MCP
server process and forwards the appropriate token on later requests.

Login can partially succeed. Its response contains ``logged_in`` and ``errors``
objects for checking each service. The top-level ``success`` value is only true
when all three service logins succeed.

``sim2l_run_simulation`` also forwards available cache and results tokens to the
catalog service so the execution can use those downstream services.

.. important::

   Authentication state is process-local. A long-running server shared by
   multiple clients would also share its stored service tokens. Use a dedicated
   MCP server process per trusted client or session, and use TLS when connecting
   to remote sim2l services.

Programmatic Use
----------------

The gateway can also be used directly without installing or importing the MCP
SDK:

.. code-block:: python

   from sim2l.mcp import Sim2LMCPGateway

   gateway = Sim2LMCPGateway(
       catalog_url="http://localhost:8002",
       results_url="http://localhost:8003",
       cache_url="http://localhost:8001",
       timeout=30,
   )

   login = gateway.login("username", "password")
   simulations = gateway.search_simulations(query="thermal", limit=10)
   result = gateway.run_simulation(
       "thermal_sim",
       version="1.0.0",
       params={"temperature": 350},
   )

Direct gateway calls raise HTTP request errors when a service request fails.
``get_result`` is the exception: it returns ``None`` when the execution ID is
not found.

Troubleshooting
---------------

Optional dependency is not installed
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Install the MCP extra in the same Python environment that provides the
``sim2l`` command:

.. code-block:: bash

   python -m pip install "sim2l[mcp]"

Service connection fails
^^^^^^^^^^^^^^^^^^^^^^^^

Confirm that each service URL is reachable from the MCP server process and that
the cache, catalog, and results services are running. Increase ``--timeout`` for
slow remote services.

Tool call is unauthorized
^^^^^^^^^^^^^^^^^^^^^^^^^

Call ``sim2l_login`` and inspect both ``logged_in`` and ``errors`` in its
response. A successful login to one service does not authenticate calls to the
other services.
