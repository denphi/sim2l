#!/usr/bin/env python3
"""
Quick Start Example for Sim2l

A simplified example showing the essential sim2l workflow:
1. Start services
2. Run a simulation
3. Check cache and results

Usage:
    python examples/quick_start_example.py
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sim2l
from sim2l.database import CacheClient, ResultsClient


def main():
    print("\n" + "="*70)
    print("SIM2L QUICK START EXAMPLE")
    print("="*70)

    # Step 1: Configure sim2l to use services
    print("\n1. Configuring sim2l services...")
    sim2l.configure(
        use_cache_service=True,
        cache_service_url="http://localhost:8001",
        use_results_service=True,
        results_service_url="http://localhost:8003"
    )
    print("   ✓ Services configured")

    # Step 2: Load a simulation
    print("\n2. Loading thermal_analysis simulation...")
    try:
        sim = sim2l.load_simulation("thermal_analysis")
        print(f"   ✓ Loaded: {sim.name} v{sim.version}")
    except Exception as e:
        print(f"   ✗ Simulation not found. Deploy it first:")
        print(f"     sim2l.deploy_simulation(notebook='thermal_simulation.ipynb', ...)")
        return

    # Step 3: Run simulation (first time - will execute)
    print("\n3. Running simulation (first time)...")
    params = {
        "temperature": 300,
        "power": 15,
        "iterations": 200,
        "grid_size": 30
    }

    print(f"   Parameters: {params}")
    start_time = time.time()
    result1 = sim.run(**params)
    time1 = time.time() - start_time

    print(f"   ✓ Completed in {time1:.2f}s")
    print(f"   Max temperature: {result1.outputs.max_temperature:.2f} K")
    print(f"   Avg temperature: {result1.outputs.avg_temperature:.2f} K")
    print(f"   Converged: {result1.outputs.converged}")

    # Step 4: Run same simulation (should hit cache)
    print("\n4. Running same simulation again (should use cache)...")
    start_time = time.time()
    result2 = sim.run(**params)
    time2 = time.time() - start_time

    print(f"   ✓ Completed in {time2:.2f}s")
    print(f"   Cache speedup: {time1/time2:.1f}x faster")

    # Verify results are identical
    same_results = (
        result1.outputs.max_temperature == result2.outputs.max_temperature and
        result1.outputs.avg_temperature == result2.outputs.avg_temperature
    )
    print(f"   Results match: {same_results}")

    # Step 5: Query results database
    print("\n5. Querying results database...")
    results_client = ResultsClient(service_url="http://localhost:8003")

    search_results = results_client.search(
        simulation_name="thermal_analysis",
        limit=5
    )

    print(f"   Found {len(search_results)} simulation runs")

    for i, res in enumerate(search_results[:3], 1):
        print(f"\n   Run {i}:")
        print(f"     ID: {res['run_id']}")
        print(f"     Timestamp: {res.get('timestamp', 'N/A')}")

    # Step 6: Get parameter statistics
    print("\n6. Parameter statistics:")
    param_stats = results_client.get_parameter_stats("thermal_analysis")

    for param_name in ['temperature', 'power']:
        if param_name in param_stats:
            stats = param_stats[param_name]
            print(f"   {param_name}:")
            print(f"     Range: {stats.get('min', 'N/A')} - {stats.get('max', 'N/A')}")
            print(f"     Average: {stats.get('avg', 'N/A'):.2f}" if stats.get('avg') else f"     Average: N/A")
            print(f"     Count: {stats.get('count', 0)}")

    print("\n" + "="*70)
    print("QUICK START COMPLETE")
    print("="*70)
    print("\nNext steps:")
    print("  - Try different parameters: sim.run(temperature=400, power=25, ...)")
    print("  - Explore the cache: CacheClient().get_cached_runs('thermal_analysis')")
    print("  - Query results: ResultsClient().search(simulation_name='...')")
    print("  - See complete_workflow_example.py for more advanced usage")


if __name__ == "__main__":
    main()
