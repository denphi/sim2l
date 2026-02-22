#!/usr/bin/env python3
# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Quick test script to populate the dashboard with sample data

This script:
1. Checks service health
2. Registers a simple simulation
3. Runs it multiple times with different parameters
4. Verifies data appears in all services
5. Prints dashboard URLs

Usage:
    python3 tests/manual/dashboard_data_population_demo.py
"""

import sys
import time
from pathlib import Path

import requests

# Add repository root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sim2l


def check_services():
    """Check if all services are running"""
    print("\n" + "="*60)
    print("CHECKING SERVICES")
    print("="*60)

    services = {
        'Cache': 'http://localhost:8001',
        'Catalog': 'http://localhost:8002',
        'Results': 'http://localhost:8003',
    }

    all_healthy = True
    for name, url in services.items():
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                data = response.json()
                backend = data.get('backend', 'unknown')
                print(f"  ✓ {name:10s} service: HEALTHY ({backend})")
            else:
                print(f"  ✗ {name:10s} service: UNHEALTHY (HTTP {response.status_code})")
                all_healthy = False
        except Exception as e:
            print(f"  ✗ {name:10s} service: DOWN ({e})")
            all_healthy = False

    if not all_healthy:
        print("\n✗ Not all services are running!")
        print("\nPlease start the services first:")
        print("  cd examples")
        print("  python3 -m sim2l.services.cache_service --backend postgresql --db-url postgresql://sim2l:sim2l_password@localhost/sim2l_cache --no-auth --port 8001 &")
        print("  python3 -m sim2l.services.catalog_service --port 8002 &")
        print("  python3 -m sim2l.services.results_service --backend postgresql --db-url postgresql://sim2l:sim2l_password@localhost:5432/sim2l_results --no-auth --port 8003 &")
        sys.exit(1)

    print("\n✓ All services are running!")
    return True


def configure_sim2l():
    """Configure sim2l to use services"""
    print("\n" + "="*60)
    print("CONFIGURING SIM2L")
    print("="*60)

    sim2l.configure(
        cache_service_url="http://localhost:8001",
        catalog_service_url="http://localhost:8002",
        results_service_url="http://localhost:8003",
        debug_mode=False  # Set to True for verbose logging
    )

    print("  ✓ Cache service: http://localhost:8001")
    print("  ✓ Catalog service: http://localhost:8002")
    print("  ✓ Results service: http://localhost:8003")


def create_test_simulation():
    """Load existing thermal_analysis simulation"""
    print("\n" + "="*60)
    print("LOADING TEST SIMULATION")
    print("="*60)

    try:
        # Try to load existing simulation
        sim = sim2l.load_simulation("thermal_analysis")
        print(f"  ✓ Loaded simulation: thermal_analysis")
        return sim
    except Exception as e:
        print(f"  ✗ Could not load thermal_analysis: {e}")
        print("\n  You need to deploy thermal_analysis first.")
        print("  Run: python3 examples/complete_workflow_postgresql.py")
        sys.exit(1)


def run_test_cases(sim):
    """Run multiple test cases"""
    print("\n" + "="*60)
    print("RUNNING TEST CASES")
    print("="*60)

    # Import executor
    from sim2l.executor import NotebookExecutor

    # Create executor with both caching and results registration
    executor = NotebookExecutor(cache=True, register_results=True)
    print("  ✓ Created executor with caching and results registration")

    # Test cases for thermal_analysis
    test_cases = [
        {"temperature": 300, "power": 10, "grid_size": 20, "iterations": 100},
        {"temperature": 350, "power": 15, "grid_size": 20, "iterations": 100},
        {"temperature": 300, "power": 10, "grid_size": 20, "iterations": 100},  # Duplicate - cache hit
        {"temperature": 400, "power": 20, "grid_size": 20, "iterations": 100},
        {"temperature": 350, "power": 15, "grid_size": 20, "iterations": 100},  # Duplicate - cache hit
    ]

    print(f"\n  Running {len(test_cases)} test cases...\n")

    results = []
    cache_hits = 0

    for i, params in enumerate(test_cases, 1):
        start = time.time()
        result = sim.run(**params, executor=executor)
        exec_time = time.time() - start

        # Detect cache hits (fast execution)
        is_cached = exec_time < 1.0
        if is_cached:
            cache_hits += 1

        status_icon = "⚡" if is_cached else "🔄"
        cache_label = "CACHE HIT" if is_cached else "NEW RUN  "

        print(f"  {i}. T={params['temperature']:>3}K, P={params['power']:>2}W → {status_icon} {cache_label} ({exec_time:.3f}s)")

        results.append({
            'params': params,
            'result': result.outputs if result.outputs else {},
            'cached': is_cached,
            'time': exec_time
        })

    print(f"\n  ✓ Completed {len(test_cases)} runs")
    print(f"  ✓ Cache hits: {cache_hits}")
    print(f"  ✓ New executions: {len(test_cases) - cache_hits}")

    return results


def verify_data():
    """Verify data is in all services"""
    print("\n" + "="*60)
    print("VERIFYING DATA")
    print("="*60)

    # Check catalog
    try:
        response = requests.get("http://localhost:8002/simulations/search?query=test")
        if response.status_code == 200:
            sims = response.json()
            if isinstance(sims, list):
                count = len(sims)
            else:
                count = len(sims.get('simulations', []))
            print(f"  ✓ Catalog: {count} simulation(s) registered")
    except Exception as e:
        print(f"  ✗ Catalog check failed: {e}")

    # Check cache
    try:
        response = requests.get("http://localhost:8001/cache/stats")
        if response.status_code == 200:
            stats = response.json()
            entries = stats.get('total_entries', 0)
            hits = stats.get('total_hits', 0)
            hit_rate = stats.get('hit_rate_percent', 0)
            print(f"  ✓ Cache: {entries} entries, {hits} hits ({hit_rate}% hit rate)")
    except Exception as e:
        print(f"  ✗ Cache check failed: {e}")

    # Check results
    try:
        response = requests.post(
            "http://localhost:8003/search",
            headers={'Content-Type': 'application/json'},
            json={'simulation_name': 'test_simulation', 'limit': 10}
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            print(f"  ✓ Results: {len(results)} execution(s) recorded")
    except Exception as e:
        print(f"  ✗ Results check failed: {e}")

    # Check overview stats
    try:
        response = requests.get("http://localhost:8002/statistics/overview")
        if response.status_code == 200:
            stats = response.json()
            total_sims = stats.get('total_simulations', 0)
            total_execs = stats.get('total_executions', 0)
            success = stats.get('successful_executions', 0)
            print(f"  ✓ Overview: {total_sims} simulations, {total_execs} executions, {success} successful")
    except Exception as e:
        print(f"  ✗ Overview check failed: {e}")


def print_dashboard_info():
    """Print dashboard access information"""
    print("\n" + "="*60)
    print("DASHBOARD READY")
    print("="*60)

    print("\n✓ Data populated successfully!")
    print("\nOpen these URLs in your browser:")
    print("\n  📊 Dashboard (Overview):")
    print("     http://localhost:3000/")
    print("\n  💾 Cache Service:")
    print("     http://localhost:3000/cache")
    print("\n  📋 Results Service:")
    print("     http://localhost:3000/results")
    print("\n  📁 Catalog Service:")
    print("     http://localhost:3000/catalog")

    print("\n" + "="*60)
    print("You should now see data in all dashboard pages!")
    print("="*60)


def main():
    """Main execution"""
    print("\n" + "="*60)
    print("SIM2L DASHBOARD TEST DATA GENERATOR")
    print("="*60)

    try:
        # Check services
        check_services()

        # Configure sim2l
        configure_sim2l()

        # Create simulation
        sim = create_test_simulation()

        # Run test cases
        results = run_test_cases(sim)

        # Verify data
        verify_data()

        # Print dashboard info
        print_dashboard_info()

    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
