#!/usr/bin/env python3
# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Complete Sim2l Workflow Example

This example demonstrates the full sim2l workflow:
1. Start all database services (Cache, Catalog, Results)
2. Deploy the thermal_simulation.ipynb
3. Run simulations with different input parameters
4. Use caching to retrieve previously computed results
5. Explore the results database
6. Query and analyze simulation outputs

Prerequisites:
    pip install sim2l papermill matplotlib

Usage:
    python examples/complete_workflow_example.py
"""

import os
import sys
import time
import sqlite3
from pathlib import Path
import subprocess
import signal
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import sim2l
from sim2l.database import CacheClient, ResultsClient, FileManager


class ServiceManager:
    """Manages the lifecycle of sim2l services"""

    def __init__(self):
        self.processes = {}
        self.base_dir = Path(__file__).parent.parent

    def start_services(self):
        """Start all sim2l services"""
        print("\n" + "="*70)
        print("STARTING SIM2L SERVICES")
        print("="*70)

        services = {
            'cache': ('sim2l.services.cache_service', 8001),
            'catalog': ('sim2l.services.catalog_service', 8002),
            'results': ('sim2l.services.results_service', 8003),
        }

        for name, (module, port) in services.items():
            print(f"\nStarting {name.upper()} service on port {port}...")

            # Start service as subprocess
            proc = subprocess.Popen(
                [sys.executable, '-m', module],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, 'FLASK_ENV': 'development'}
            )
            self.processes[name] = proc

            # Wait for service to be ready
            if self.wait_for_service(port):
                print(f"  ✓ {name.upper()} service ready at http://localhost:{port}")
            else:
                print(f"  ✗ {name.upper()} service failed to start")
                self.stop_services()
                raise RuntimeError(f"Failed to start {name} service")

        print("\n✓ All services started successfully!")

    def wait_for_service(self, port, timeout=10):
        """Wait for a service to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f'http://localhost:{port}/health')
                if response.status_code == 200:
                    return True
            except requests.ConnectionError:
                time.sleep(0.5)
        return False

    def stop_services(self):
        """Stop all running services"""
        print("\n" + "="*70)
        print("STOPPING SERVICES")
        print("="*70)

        for name, proc in self.processes.items():
            print(f"Stopping {name.upper()} service...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
                print(f"  ✓ {name.upper()} stopped")
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"  ✓ {name.upper()} killed")

        self.processes.clear()
        print("\n✓ All services stopped")


def deploy_thermal_simulation():
    """Deploy the thermal simulation notebook"""
    print("\n" + "="*70)
    print("DEPLOYING THERMAL SIMULATION")
    print("="*70)

    notebook_path = Path(__file__).parent / "thermal_simulation.ipynb"

    if not notebook_path.exists():
        print(f"✗ Notebook not found: {notebook_path}")
        return None

    print(f"\nDeploying notebook: {notebook_path.name}")

    try:
        sim_id = sim2l.deploy_simulation(
            notebook=str(notebook_path),
            name="thermal_analysis",
            version="1.0.0",
            description="2D thermal diffusion simulation with finite difference method",
            author="Sim2l Team",
            tags=["physics", "thermal", "finite-difference", "diffusion"]
        )

        print(f"✓ Simulation deployed successfully!")
        print(f"  Simulation ID: {sim_id}")
        print(f"  Name: thermal_analysis")
        print(f"  Version: 1.0.0")

        return sim_id

    except ValueError as e:
        if "already exists" in str(e):
            print(f"ℹ Simulation already exists, loading it instead...")
            sim = sim2l.load_simulation("thermal_analysis")
            sim_id = sim.id if hasattr(sim, 'id') else 0
            print(f"✓ Loaded existing simulation")
            print(f"  Simulation ID: {sim_id}")
            print(f"  Name: thermal_analysis")
            print(f"  Version: 1.0.0")
            return sim_id
        else:
            print(f"✗ Deployment failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    except Exception as e:
        print(f"✗ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_simulations_with_caching():
    """Run thermal simulations with different parameters and demonstrate caching"""
    print("\n" + "="*70)
    print("RUNNING SIMULATIONS WITH CACHING")
    print("="*70)

    # Load the deployed simulation
    print("\nLoading simulation...")
    sim = sim2l.load_simulation("thermal_analysis")
    print(f"✓ Loaded: {sim.name} v{sim.version}")

    # Create executor for notebook-based simulations
    from sim2l.executor import NotebookExecutor
    executor = NotebookExecutor(cache=True)
    print(f"✓ Created NotebookExecutor with caching enabled")

    # Define test cases
    test_cases = [
        {"temperature": 300, "power": 10, "iterations": 200, "grid_size": 30},
        {"temperature": 350, "power": 20, "iterations": 200, "grid_size": 30},
        {"temperature": 300, "power": 10, "iterations": 200, "grid_size": 30},  # Duplicate - should hit cache
        {"temperature": 400, "power": 15, "iterations": 300, "grid_size": 40},
        {"temperature": 350, "power": 20, "iterations": 200, "grid_size": 30},  # Duplicate - should hit cache
    ]

    results = []

    for i, params in enumerate(test_cases, 1):
        print(f"\n{'─'*70}")
        print(f"Test Case {i}/{len(test_cases)}")
        print(f"{'─'*70}")
        print(f"Parameters:")
        for key, value in params.items():
            print(f"  {key}: {value}")

        # Run simulation
        start_time = time.time()
        result = sim.run(**params, executor=executor)
        elapsed_time = time.time() - start_time

        # Check if result was cached
        cache_status = "CACHE HIT" if elapsed_time < 1.0 else "NEW RUN"

        print(f"\nResult:")
        print(f"  Status: {cache_status}")
        print(f"  Execution time: {elapsed_time:.2f}s")
        print(f"  Max temperature: {result.outputs.max_temperature:.2f} K")
        print(f"  Avg temperature: {result.outputs.avg_temperature:.2f} K")
        print(f"  Converged: {result.outputs.converged}")
        print(f"  Iterations: {result.outputs.iterations_to_convergence}")

        results.append({
            'params': params,
            'result': result,
            'elapsed_time': elapsed_time,
            'cache_hit': elapsed_time < 1.0
        })

    # Summary
    print(f"\n{'='*70}")
    print("EXECUTION SUMMARY")
    print(f"{'='*70}")
    print(f"Total runs: {len(results)}")
    print(f"Cache hits: {sum(1 for r in results if r['cache_hit'])}")
    print(f"New executions: {sum(1 for r in results if not r['cache_hit'])}")
    print(f"Time saved by caching: {sum(r['elapsed_time'] for r in results if not r['cache_hit']) * sum(1 for r in results if r['cache_hit']):.2f}s (estimated)")

    return results


def explore_cache_database():
    """Explore the cache database to see cached results"""
    print("\n" + "="*70)
    print("EXPLORING CACHE DATABASE")
    print("="*70)

    try:
        # Connect to cache service
        cache_client = CacheClient(service_url="http://localhost:8001")

        print("\nQuerying cache database...")

        # Get cache statistics
        response = requests.get("http://localhost:8001/stats")
        if response.status_code == 200:
            stats = response.json()
            print(f"\nCache Statistics:")
            print(f"  Total cached entries: {stats.get('total_entries', 0)}")
            print(f"  Total size: {stats.get('total_size', 0)} bytes")

        # List all cached simulations
        response = requests.get("http://localhost:8001/cache")
        if response.status_code == 200:
            cached_items = response.json()
            print(f"\nCached Simulations: {len(cached_items)} items")

            for i, item in enumerate(cached_items[:5], 1):  # Show first 5
                print(f"\n  {i}. Simulation: {item.get('simulation_name', 'N/A')}")
                print(f"     Version: {item.get('version', 'N/A')}")
                print(f"     SQUID ID: {item.get('squid_id', 'N/A')[:16]}...")
                print(f"     Cached at: {item.get('created_at', 'N/A')}")

        print("\n✓ Cache exploration complete")

    except Exception as e:
        print(f"✗ Cache exploration failed: {e}")
        import traceback
        traceback.print_exc()


def explore_results_database():
    """Explore the results database to analyze simulation outputs"""
    print("\n" + "="*70)
    print("EXPLORING RESULTS DATABASE")
    print("="*70)

    try:
        # Connect to results service
        results_client = ResultsClient(base_url="http://localhost:8003")

        print("\nQuerying results database...")

        # Search for all thermal_analysis results
        search_results = results_client.search(
            simulation_name="thermal_analysis",
            limit=10
        )

        print(f"\nFound {len(search_results)} simulation results:")

        for i, result in enumerate(search_results, 1):
            print(f"\n  {i}. Run ID: {result['run_id']}")
            print(f"     Timestamp: {result.get('timestamp', 'N/A')}")
            print(f"     Parameters:")

            # Get full result details
            full_result = results_client.get_result(result['run_id'])

            if 'inputs' in full_result:
                for key, value in full_result['inputs'].items():
                    print(f"       - {key}: {value}")

            if 'outputs' in full_result:
                print(f"     Key Outputs:")
                outputs = full_result['outputs']
                print(f"       - Max temp: {outputs.get('max_temperature', 'N/A')} K")
                print(f"       - Avg temp: {outputs.get('avg_temperature', 'N/A')} K")
                print(f"       - Converged: {outputs.get('converged', 'N/A')}")

        # Get parameter statistics
        print(f"\n{'─'*70}")
        print("PARAMETER STATISTICS")
        print(f"{'─'*70}")

        param_stats = results_client.get_parameter_stats("thermal_analysis")

        for param_name, stats in param_stats.items():
            print(f"\n  {param_name}:")
            print(f"    Min: {stats.get('min', 'N/A')}")
            print(f"    Max: {stats.get('max', 'N/A')}")
            print(f"    Avg: {stats.get('avg', 'N/A'):.2f}" if stats.get('avg') else "    Avg: N/A")
            print(f"    Count: {stats.get('count', 0)}")

        print("\n✓ Results exploration complete")

    except Exception as e:
        print(f"✗ Results exploration failed: {e}")
        import traceback
        traceback.print_exc()


def explore_file_manager():
    """Explore files associated with simulation runs"""
    print("\n" + "="*70)
    print("EXPLORING FILE MANAGER")
    print("="*70)

    try:
        # Initialize file manager
        file_manager = FileManager()

        print("\nQuerying file database...")

        # List files for recent simulations
        files = file_manager.list_folder(limit=10)

        print(f"\nFound {len(files)} files:")

        for i, file_info in enumerate(files, 1):
            print(f"\n  {i}. File: {file_info.get('filename', 'N/A')}")
            print(f"     Run ID: {file_info.get('run_id', 'N/A')}")
            print(f"     Type: {file_info.get('file_type', 'N/A')}")
            print(f"     Size: {file_info.get('size', 0)} bytes")
            print(f"     Created: {file_info.get('created_at', 'N/A')}")

        print("\n✓ File exploration complete")

    except Exception as e:
        print(f"✗ File exploration failed: {e}")
        import traceback
        traceback.print_exc()


def analyze_results(results):
    """Analyze and visualize results"""
    print("\n" + "="*70)
    print("ANALYZING RESULTS")
    print("="*70)

    print("\nComparison of simulation results:")
    print(f"\n{'Case':<6} {'Temp(K)':<10} {'Power(W)':<10} {'Iter':<8} "
          f"{'Max T(K)':<12} {'Avg T(K)':<12} {'Conv':<8} {'Time(s)':<10} {'Cached'}")
    print("─" * 110)

    for i, r in enumerate(results, 1):
        params = r['params']
        outputs = r['result'].outputs
        cached = "YES" if r['cache_hit'] else "NO"

        print(f"{i:<6} {params['temperature']:<10} {params['power']:<10} "
              f"{params['iterations']:<8} {outputs.max_temperature:<12.2f} "
              f"{outputs.avg_temperature:<12.2f} {str(outputs.converged):<8} "
              f"{r['elapsed_time']:<10.2f} {cached}")

    # Performance analysis
    print(f"\n{'─'*70}")
    print("PERFORMANCE INSIGHTS")
    print(f"{'─'*70}")

    new_runs = [r for r in results if not r['cache_hit']]
    cached_runs = [r for r in results if r['cache_hit']]

    if new_runs:
        avg_new_time = sum(r['elapsed_time'] for r in new_runs) / len(new_runs)
        print(f"Average execution time (new runs): {avg_new_time:.2f}s")

    if cached_runs:
        avg_cached_time = sum(r['elapsed_time'] for r in cached_runs) / len(cached_runs)
        print(f"Average execution time (cached): {avg_cached_time:.2f}s")

        if new_runs:
            speedup = avg_new_time / avg_cached_time
            print(f"Cache speedup: {speedup:.1f}x faster")

    # Result quality analysis
    print(f"\n{'─'*70}")
    print("SIMULATION QUALITY")
    print(f"{'─'*70}")

    all_converged = all(r['result'].outputs.converged for r in results)
    convergence_rate = sum(1 for r in results if r['result'].outputs.converged) / len(results) * 100

    print(f"Convergence rate: {convergence_rate:.1f}%")
    print(f"All simulations converged: {all_converged}")

    avg_iterations = sum(r['result'].outputs.iterations_to_convergence for r in results) / len(results)
    print(f"Average iterations to convergence: {avg_iterations:.1f}")


def main():
    """Run the complete workflow example"""

    print("\n" + "="*70)
    print("SIM2L COMPLETE WORKFLOW EXAMPLE")
    print("="*70)
    print("\nThis example demonstrates:")
    print("  1. Starting all sim2l database services")
    print("  2. Deploying a simulation from a Jupyter notebook")
    print("  3. Running simulations with various parameters")
    print("  4. Automatic caching of results")
    print("  5. Exploring the cache database")
    print("  6. Exploring the results database")
    print("  7. Analyzing simulation outputs")

    # Initialize service manager
    service_manager = ServiceManager()

    try:
        # Step 1: Start services
        service_manager.start_services()

        # Configure sim2l to use the services
        sim2l.configure(
            cache_service_url="http://localhost:8001",
            catalog_service_url="http://localhost:8002"
        )

        # Step 2: Deploy simulation
        sim_id = deploy_thermal_simulation()

        if sim_id is None:
            print("\n✗ Simulation deployment failed. Exiting.")
            return

        # Step 3: Run simulations with caching
        results = run_simulations_with_caching()

        # Step 4: Explore cache database
        explore_cache_database()

        # Step 5: Explore results database
        explore_results_database()

        # Step 6: Explore file manager
        explore_file_manager()

        # Step 7: Analyze results
        analyze_results(results)

        # Final summary
        print("\n" + "="*70)
        print("WORKFLOW COMPLETE")
        print("="*70)
        print("\n✓ Successfully demonstrated:")
        print("  - Service management (start/stop)")
        print("  - Simulation deployment from notebook")
        print("  - Parameterized execution")
        print("  - Automatic result caching")
        print("  - Database exploration and querying")
        print("  - Performance analysis")
        print("\nAll sim2l services are ready for production use!")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")

    except Exception as e:
        print(f"\n✗ Error during workflow: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Always stop services
        service_manager.stop_services()

        print("\n" + "="*70)
        print("Example completed. Thank you for using sim2l!")
        print("="*70)


if __name__ == "__main__":
    main()
