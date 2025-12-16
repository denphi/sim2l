#!/usr/bin/env python3
"""
Example: Using the Results Service to register and search simulation results.

The Results Service introspects simulation runs, extracts parameter schemas
and values, and stores them in a searchable database. This enables powerful
queries like:
- Find all runs where temperature > 300
- Get statistics for output parameters
- Search by combinations of input/output values

This is the modern equivalent of registerSquidpgSimtool.
"""

from sim2l.database import ResultsClient, RunDatabase, get_session_manager


def example_1_register_result():
    """Register a simulation result with the Results Service."""
    print("=" * 60)
    print("Example 1: Register a simulation result")
    print("=" * 60)

    # Create session
    session = get_session_manager().create_anonymous_session()

    # Initialize Results Client
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    # Check service health
    health = client.health_check()
    print(f"\nService status: {health['status']}")
    print(f"Backend: {health.get('backend', 'unknown')}")

    # Register a result (assumes run database exists)
    execution_id = "exec-2024-001"

    try:
        result = client.register_result(execution_id)
        print(f"\n✓ Registered execution {execution_id}")
        print(f"  Result ID: {result['result_id']}")
        print(f"  Schema ID: {result['schema_id']}")
    except Exception as e:
        print(f"\n✗ Failed to register: {e}")


def example_2_search_by_parameters():
    """Search for results by input/output parameter values."""
    print("=" * 60)
    print("Example 2: Search by parameter values")
    print("=" * 60)

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    # Search by input parameters
    print("\nSearching for runs with temperature=350...")
    results = client.search(
        simulation_name="thermal_sim",
        input_filters={'temperature': 350}
    )

    print(f"Found {len(results)} matching results:")
    for result in results[:5]:  # Show first 5
        print(f"  - {result['execution_id']}")
        print(f"    Inputs: {result['input_params']}")
        print(f"    Outputs: {result['output_params']}")

    # Search by output parameters
    print("\nSearching for runs with max_stress=150...")
    results = client.search(
        simulation_name="thermal_sim",
        output_filters={'max_stress': 150}
    )

    print(f"Found {len(results)} matching results")


def example_3_parameter_statistics():
    """Get statistics for a parameter across all runs."""
    print("=" * 60)
    print("Example 3: Parameter statistics")
    print("=" * 60)

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    # Get statistics for an output parameter
    stats = client.get_parameter_stats(
        simulation_name="thermal_sim",
        param_name="max_stress",
        param_class="output"
    )

    print(f"\nStatistics for 'max_stress' parameter:")
    if stats.get('count', 0) > 0:
        print(f"  Count: {stats['count']}")
        print(f"  Min: {stats['min_value']}")
        print(f"  Max: {stats['max_value']}")
        print(f"  Average: {stats['avg_value']}")
    else:
        print("  No data available")


def example_4_get_specific_result():
    """Retrieve a specific result by execution ID."""
    print("=" * 60)
    print("Example 4: Get specific result")
    print("=" * 60)

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    execution_id = "exec-2024-001"
    result = client.get_result(execution_id)

    if result:
        print(f"\nResult for {execution_id}:")
        print(f"  Simulation: {result['simulation_name']} v{result['simulation_version']}")
        print(f"  Status: {result['status']}")
        print(f"  Duration: {result['duration_seconds']}s")
        print(f"\n  Input Parameters:")
        for key, value in result['input_params'].items():
            print(f"    {key}: {value}")
        print(f"\n  Output Parameters:")
        for key, value in (result['output_params'] or {}).items():
            print(f"    {key}: {value}")
    else:
        print(f"\n✗ Result not found: {execution_id}")


def example_5_batch_registration():
    """Register multiple results in batch."""
    print("=" * 60)
    print("Example 5: Batch result registration")
    print("=" * 60)

    session = get_session_manager().create_anonymous_session()
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )

    # Assume we have multiple execution IDs
    execution_ids = [
        "exec-2024-001",
        "exec-2024-002",
        "exec-2024-003"
    ]

    print(f"\nRegistering {len(execution_ids)} results...")

    success_count = 0
    for exec_id in execution_ids:
        try:
            result = client.register_result(exec_id)
            print(f"  ✓ {exec_id}")
            success_count += 1
        except Exception as e:
            print(f"  ✗ {exec_id}: {e}")

    print(f"\nRegistered {success_count}/{len(execution_ids)} results")


def example_6_workflow():
    """Complete workflow: run simulation, register, search."""
    print("=" * 60)
    print("Example 6: Complete workflow")
    print("=" * 60)

    # Step 1: Authenticate
    session = get_session_manager().create_anonymous_session()
    print("1. Created session")

    # Step 2: Initialize Results Client
    client = ResultsClient(
        "http://localhost:8003",
        session_id=session.session_id
    )
    print("2. Connected to Results Service")

    # Step 3: Run simulation (simulated here)
    # In real code: result = sim.run(temperature=350)
    execution_id = "exec-2024-001"
    print(f"3. Simulation completed: {execution_id}")

    # Step 4: Register result
    try:
        reg_result = client.register_result(execution_id)
        print(f"4. Registered result (ID: {reg_result['result_id']})")
    except Exception as e:
        print(f"4. Registration failed: {e}")
        return

    # Step 5: Verify registration
    result = client.get_result(execution_id)
    if result:
        print(f"5. Verified registration")
        print(f"   Input params: {list(result['input_params'].keys())}")
        print(f"   Output params: {list((result['output_params'] or {}).keys())}")
    else:
        print("5. Verification failed")

    # Step 6: Search for similar results
    # Example: Find other runs with same input parameter
    if result and result['input_params']:
        first_param = list(result['input_params'].keys())[0]
        param_value = result['input_params'][first_param]

        similar = client.search(
            simulation_name=result['simulation_name'],
            input_filters={first_param: param_value}
        )
        print(f"6. Found {len(similar)} runs with {first_param}={param_value}")


def example_7_introspection_details():
    """Show what gets introspected from a run."""
    print("=" * 60)
    print("Example 7: Introspection details")
    print("=" * 60)

    execution_id = "exec-2024-001"

    try:
        # Direct access to run database
        run_db = RunDatabase(execution_id)

        # Get what will be introspected
        summary = run_db.get_summary()
        inputs = run_db.get_inputs()
        outputs = run_db.get_outputs()

        print(f"\nIntrospection for {execution_id}:")
        print(f"\nSimulation: {summary['simulation_name']} v{summary['simulation_version']}")
        print(f"Status: {summary['status']}")

        print(f"\nInput Parameters ({len(inputs)}):")
        for inp in inputs:
            print(f"  - {inp['name']}: {inp['value']} ({inp['field_type']})")
            if inp.get('units'):
                print(f"    Units: {inp['units']}")

        print(f"\nOutput Parameters ({len(outputs)}):")
        for out in outputs:
            print(f"  - {out['name']}: {out['value']} ({out['field_type']})")
            if out.get('units'):
                print(f"    Units: {out['units']}")

        print("\nThis data will be extracted and stored in the Results Service")

    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == '__main__':
    print("\nSim2l Results Service Examples")
    print("=" * 60)
    print()

    print("NOTE: These examples require:")
    print("1. Results Service running on http://localhost:8003")
    print("2. Run databases to exist for the execution IDs")
    print()

    # Run examples
    try:
        example_1_register_result()
    except Exception as e:
        print(f"Example 1 failed: {e}\n")

    try:
        example_2_search_by_parameters()
    except Exception as e:
        print(f"Example 2 failed: {e}\n")

    try:
        example_3_parameter_statistics()
    except Exception as e:
        print(f"Example 3 failed: {e}\n")

    try:
        example_4_get_specific_result()
    except Exception as e:
        print(f"Example 4 failed: {e}\n")

    try:
        example_5_batch_registration()
    except Exception as e:
        print(f"Example 5 failed: {e}\n")

    try:
        example_6_workflow()
    except Exception as e:
        print(f"Example 6 failed: {e}\n")

    try:
        example_7_introspection_details()
    except Exception as e:
        print(f"Example 7 failed: {e}\n")

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)
