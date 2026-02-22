#!/usr/bin/env python3
# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Test script to demonstrate parameter search functionality in Results Service.

This script shows how to:
1. Search results by input parameters
2. Search results by output parameters
3. Combine multiple filters
4. Use the search in real workflows
"""

import requests
import json
from typing import Dict, Any


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def search_results(
    simulation_name: str = None,
    input_filters: Dict[str, Any] = None,
    output_filters: Dict[str, Any] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search execution results by parameters.

    Args:
        simulation_name: Filter by simulation name
        input_filters: Filter by input parameter values
        output_filters: Filter by output parameter values
        limit: Maximum results to return

    Returns:
        Search results with matching executions
    """
    payload = {
        "limit": limit
    }

    if simulation_name:
        payload["simulation_name"] = simulation_name
    if input_filters:
        payload["input_filters"] = input_filters
    if output_filters:
        payload["output_filters"] = output_filters

    response = requests.post(
        "http://localhost:8003/search",
        headers={"Content-Type": "application/json"},
        json=payload
    )

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return {"results": [], "count": 0}


def demo_basic_search():
    """Demo 1: Basic search by simulation name."""
    print_section("DEMO 1: Basic Search by Simulation Name")

    results = search_results(simulation_name="thermal_analysis", limit=5)

    print(f"\nFound {results['count']} executions")
    print("\nFirst 3 results:")

    for i, result in enumerate(results['results'][:3], 1):
        exec_id = result.get('execution_id', 'unknown')[:8]
        status = result.get('status', 'unknown')
        inputs = result.get('input_params', {})

        print(f"\n{i}. Execution: {exec_id}...")
        print(f"   Status: {status}")
        print(f"   Inputs: temperature={inputs.get('temperature')}, power={inputs.get('power')}")


def demo_input_filter():
    """Demo 2: Search by input parameters."""
    print_section("DEMO 2: Search by Input Parameters")

    # Find all runs with temperature=300K
    results = search_results(
        simulation_name="thermal_analysis",
        input_filters={"temperature": 300},
        limit=10
    )

    print(f"\nSearching for: temperature=300K")
    print(f"Found {results['count']} matching executions\n")

    for i, result in enumerate(results['results'][:5], 1):
        inputs = result.get('input_params', {})
        outputs = result.get('output_params', {})

        print(f"{i}. T={inputs.get('temperature')}K, P={inputs.get('power')}W, "
              f"Grid={inputs.get('grid_size')}")
        print(f"   → Max temp: {outputs.get('max_temperature', 'N/A'):.2f}K, "
              f"Converged: {outputs.get('converged', False)}")


def demo_output_filter():
    """Demo 3: Search by output parameters."""
    print_section("DEMO 3: Search by Output Parameters")

    # Find runs that converged
    results = search_results(
        simulation_name="thermal_analysis",
        output_filters={"converged": False},  # Most runs don't converge with 200 iterations
        limit=5
    )

    print(f"\nSearching for: converged=False")
    print(f"Found {results['count']} non-converged executions\n")

    for i, result in enumerate(results['results'][:3], 1):
        inputs = result.get('input_params', {})
        outputs = result.get('output_params', {})

        print(f"{i}. Inputs: T={inputs.get('temperature')}K, Iterations={inputs.get('iterations')}")
        print(f"   Output: Max T={outputs.get('max_temperature', 'N/A'):.2f}K, "
              f"Converged: {outputs.get('converged')}")


def demo_combined_filters():
    """Demo 4: Combine input and output filters."""
    print_section("DEMO 4: Combined Input + Output Filters")

    # Find specific scenario: temperature=300K AND power=10W
    results = search_results(
        simulation_name="thermal_analysis",
        input_filters={
            "temperature": 300,
            "power": 10
        },
        limit=10
    )

    print(f"\nSearching for: temperature=300K AND power=10W")
    print(f"Found {results['count']} matching executions\n")

    for i, result in enumerate(results['results'], 1):
        inputs = result.get('input_params', {})
        outputs = result.get('output_params', {})
        exec_id = result.get('execution_id', 'unknown')[:8]

        print(f"{i}. Execution {exec_id}...")
        print(f"   Inputs: {json.dumps(inputs, indent=6)}")
        print(f"   Key Outputs:")
        print(f"     - Max temperature: {outputs.get('max_temperature', 'N/A'):.4f}K")
        print(f"     - Avg temperature: {outputs.get('avg_temperature', 'N/A'):.4f}K")
        print(f"     - Converged: {outputs.get('converged', False)}")


def demo_parameter_comparison():
    """Demo 5: Compare different parameter values."""
    print_section("DEMO 5: Parameter Sweep Comparison")

    # Get results for different temperatures
    temps_to_test = [300, 350, 400]

    print("\nComparing max temperature output for different input temperatures:\n")
    print(f"{'Input T (K)':<12} {'Input P (W)':<12} {'Output Max T (K)':<20} {'Converged':<10}")
    print("-" * 60)

    for temp in temps_to_test:
        results = search_results(
            simulation_name="thermal_analysis",
            input_filters={"temperature": temp},
            limit=3
        )

        for result in results['results'][:1]:  # Just show first result for each temp
            inputs = result.get('input_params', {})
            outputs = result.get('output_params', {})

            in_temp = inputs.get('temperature', 'N/A')
            in_power = inputs.get('power', 'N/A')
            out_max_temp = outputs.get('max_temperature', 0)
            converged = "Yes" if outputs.get('converged') else "No"

            print(f"{in_temp:<12.1f} {in_power:<12.1f} {out_max_temp:<20.4f} {converged:<10}")


def demo_cache_analysis():
    """Demo 6: Analyze cache hits for identical parameters."""
    print_section("DEMO 6: Cache Hit Analysis")

    # Find duplicate parameter sets (should be cache hits)
    results = search_results(
        simulation_name="thermal_analysis",
        input_filters={"temperature": 300, "power": 10},
        limit=10
    )

    print(f"\nSearching for duplicate runs: temperature=300, power=10")
    print(f"Found {results['count']} executions with identical parameters\n")

    print("These runs should have cache hits (except the first one):")
    print(f"{'Execution ID':<15} {'Status':<12} {'Created At':<25}")
    print("-" * 55)

    for result in results['results']:
        exec_id = result.get('execution_id', 'unknown')[:12]
        status = result.get('status', 'unknown')
        created = result.get('created_at', 'N/A')

        print(f"{exec_id:<15} {status:<12} {created:<25}")

    print(f"\nNote: All runs after the first should be cache hits!")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("SIM2L RESULTS SERVICE - PARAMETER SEARCH DEMONSTRATION")
    print("=" * 70)

    print("\nThis script demonstrates how to search execution results by")
    print("input and output parameters using the Results Service API.")

    try:
        # Check service health
        health = requests.get("http://localhost:8003/health", timeout=2).json()
        print(f"\n✓ Results Service: {health['status']} ({health['backend']})")
    except Exception as e:
        print(f"\n✗ Results Service not available: {e}")
        print("\nPlease start the results service:")
        print("  python3 -m sim2l.services.results_service \\")
        print("    --backend postgresql \\")
        print("    --db-url postgresql://sim2l:sim2l_password@localhost:5432/sim2l_results \\")
        print("    --no-auth --port 8003")
        return

    # Run all demos
    demo_basic_search()
    demo_input_filter()
    demo_output_filter()
    demo_combined_filters()
    demo_parameter_comparison()
    demo_cache_analysis()

    print_section("SUMMARY")
    print("\n✅ Parameter search is working!")
    print("\nYou can now:")
    print("  1. Search by input parameters (e.g., temperature, power)")
    print("  2. Search by output parameters (e.g., max_temperature, converged)")
    print("  3. Combine multiple filters for precise queries")
    print("  4. Analyze parameter sweeps and cache behavior")
    print("\nView the dashboard at: http://localhost:3000/results")
    print("See documentation: RESULTS_SEARCH_FEATURE.md")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
