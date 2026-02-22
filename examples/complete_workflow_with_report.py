#!/usr/bin/env python3
# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Complete Sim2l Workflow Example with HTML Report Generation

This example demonstrates the full sim2l workflow with comprehensive logging
and HTML report generation showing all service interactions and results.

Features:
- Detailed logging of every service interaction
- HTML report with visualizations
- Service health monitoring
- Performance metrics
- Database query results
- Cache statistics

Usage:
    python examples/complete_workflow_with_report.py
"""

import os
import sys
import time
import sqlite3
from pathlib import Path
import subprocess
import requests
from datetime import datetime
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sim2l
from sim2l.database import CacheClient, ResultsClient, FileManager
from html_report_generator import HTMLReportGenerator


class VerboseWorkflowRunner:
    """
    Runs complete sim2l workflow with detailed logging and reporting
    """

    def __init__(self):
        self.report = HTMLReportGenerator("sim2l_workflow_report.html")
        self.service_interactions = []
        self.execution_results = []
        self.timeline_events = []
        self.processes = {}
        self.start_time = time.time()

    def log_interaction(self, service: str, operation: str, status: str,
                       response_time: float = None, details: str = ""):
        """Log a service interaction"""
        interaction = {
            'timestamp': datetime.now().strftime("%H:%M:%S.%f")[:-3],
            'service': service,
            'operation': operation,
            'status': status,
            'response_time': f"{response_time:.1f}" if response_time else "N/A",
            'details': details
        }
        self.service_interactions.append(interaction)

        # Print to console
        status_symbol = "✓" if status == "success" else "✗"
        print(f"  [{interaction['timestamp']}] {status_symbol} {service.upper()}: {operation}")
        if details:
            print(f"      └─ {details}")

    def log_timeline(self, title: str, description: str):
        """Add timeline event"""
        event = {
            'time': datetime.now().strftime("%H:%M:%S"),
            'title': title,
            'description': description
        }
        self.timeline_events.append(event)

    def check_service_health(self, name: str, port: int, url: str) -> Dict[str, Any]:
        """Check service health with detailed logging"""
        print(f"\n  Checking {name.upper()} service health...")

        start = time.time()
        try:
            response = requests.get(f"{url}/health", timeout=5)
            response_time = (time.time() - start) * 1000

            if response.status_code == 200:
                self.log_interaction(
                    name, "Health Check", "success",
                    response_time, f"Status: {response.json().get('status', 'unknown')}"
                )
                return {
                    'healthy': True,
                    'port': port,
                    'url': url,
                    'response_time': response_time
                }
            else:
                self.log_interaction(
                    name, "Health Check", "failed",
                    response_time, f"HTTP {response.status_code}"
                )
                return {'healthy': False, 'port': port, 'url': url, 'response_time': response_time}

        except Exception as e:
            response_time = (time.time() - start) * 1000
            self.log_interaction(
                name, "Health Check", "failed",
                response_time, f"Error: {str(e)}"
            )
            return {'healthy': False, 'port': port, 'url': url, 'response_time': response_time}

    def start_services(self) -> Dict[str, Dict[str, Any]]:
        """Start all services with detailed logging"""
        print("\n" + "="*70)
        print("STARTING SIM2L SERVICES")
        print("="*70)

        self.log_timeline("Service Startup", "Beginning service initialization")

        services_config = {
            'cache': ('sim2l.services.cache_service', 8001, "http://localhost:8001"),
            'catalog': ('sim2l.services.catalog_service', 8002, "http://localhost:8002"),
            'results': ('sim2l.services.results_service', 8003, "http://localhost:8003"),
        }

        service_status = {}

        for name, (module, port, url) in services_config.items():
            print(f"\nStarting {name.upper()} service...")
            print(f"  Module: {module}")
            print(f"  Port: {port}")
            print(f"  URL: {url}")

            start = time.time()

            # Start service (disable auth for cache and results services in demo mode)
            cmd = [sys.executable, '-m', module]
            if name in ['cache', 'results']:
                cmd.append('--no-auth')

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, 'FLASK_ENV': 'development'}
            )
            self.processes[name] = proc

            # Wait for service to be ready
            print(f"  Waiting for service to be ready...")
            ready = self.wait_for_service(port, url)

            startup_time = time.time() - start

            if ready:
                status = self.check_service_health(name, port, url)
                service_status[name] = status
                self.log_interaction(
                    name, "Service Startup", "success",
                    startup_time * 1000, f"Ready in {startup_time:.2f}s"
                )
                print(f"  ✓ {name.upper()} service ready ({startup_time:.2f}s)")
            else:
                self.log_interaction(
                    name, "Service Startup", "failed",
                    startup_time * 1000, "Timeout waiting for service"
                )
                print(f"  ✗ {name.upper()} service failed to start")
                self.stop_services()
                raise RuntimeError(f"Failed to start {name} service")

        self.log_timeline("Services Started", f"All {len(services_config)} services operational")
        print("\n✓ All services started successfully!")

        return service_status

    def wait_for_service(self, port: int, url: str, timeout: int = 10) -> bool:
        """Wait for service to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f'{url}/health', timeout=1)
                if response.status_code == 200:
                    return True
            except (requests.ConnectionError, requests.Timeout):
                time.sleep(0.5)
        return False

    def deploy_simulation(self) -> Dict[str, Any]:
        """Deploy simulation with detailed logging"""
        print("\n" + "="*70)
        print("DEPLOYING SIMULATION")
        print("="*70)

        self.log_timeline("Simulation Deployment", "Deploying thermal_analysis from notebook")

        notebook_path = Path(__file__).parent / "thermal_simulation.ipynb"

        print(f"\nNotebook: {notebook_path.name}")
        print(f"  Path: {notebook_path}")
        print(f"  Exists: {notebook_path.exists()}")

        if not notebook_path.exists():
            self.log_interaction("deployment", "Check Notebook", "failed", 0, "Notebook not found")
            raise FileNotFoundError(f"Notebook not found: {notebook_path}")

        self.log_interaction("deployment", "Check Notebook", "success", 0, f"Found at {notebook_path}")

        print(f"  Size: {notebook_path.stat().st_size} bytes")

        # Deploy or load existing
        print("\nDeploying to database...")
        start = time.time()

        try:
            # Try to deploy new simulation
            sim_id = sim2l.deploy_simulation(
                notebook=str(notebook_path),
                name="thermal_analysis",
                version="1.0.0",
                description="2D thermal diffusion simulation with finite difference method",
                author="Sim2l Team",
                tags=["physics", "thermal", "finite-difference", "diffusion"]
            )

            deploy_time = time.time() - start

            deployment_info = {
                'sim_id': sim_id,
                'name': "thermal_analysis",
                'version': "1.0.0",
                'notebook': str(notebook_path.name),
                'description': "2D thermal diffusion simulation",
                'author': "Sim2l Team",
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            self.log_interaction(
                "deployment", "Deploy Simulation", "success",
                deploy_time * 1000, f"Simulation ID: {sim_id}"
            )
        except ValueError as e:
            if "already exists" in str(e):
                # Simulation already deployed, load it instead
                deploy_time = time.time() - start
                sim = sim2l.load_simulation("thermal_analysis")
                sim_id = sim.id if hasattr(sim, 'id') else 0

                deployment_info = {
                    'sim_id': sim_id,
                    'name': "thermal_analysis",
                    'version': "1.0.0",
                    'notebook': str(notebook_path.name),
                    'description': "2D thermal diffusion simulation (existing)",
                    'author': "Sim2l Team",
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                self.log_interaction(
                    "deployment", "Load Existing Simulation", "success",
                    deploy_time * 1000, f"Using existing simulation"
                )
                print(f"  ✓ Using existing simulation (already deployed)")
            else:
                raise

        print(f"\n✓ Simulation deployed successfully!")
        print(f"  Simulation ID: {sim_id}")
        print(f"  Name: thermal_analysis")
        print(f"  Version: 1.0.0")
        print(f"  Deployment time: {deploy_time:.2f}s")

        self.log_timeline("Deployment Complete", f"Simulation ID {sim_id} registered")

        return deployment_info

    def run_simulations(self) -> List[Dict[str, Any]]:
        """Run multiple simulations with caching"""
        print("\n" + "="*70)
        print("RUNNING SIMULATIONS")
        print("="*70)

        self.log_timeline("Execution Phase", "Running parameterized simulations")

        # Use demo session (services started with --no-auth create this automatically)
        self.demo_session_id = "demo-session"
        print(f"Using demo session (no-auth mode)")

        # Load simulation
        print("\nLoading deployed simulation...")
        start = time.time()
        sim = sim2l.load_simulation("thermal_analysis")
        load_time = time.time() - start

        self.log_interaction(
            "database", "Load Simulation", "success",
            load_time * 1000, f"Loaded {sim.name} v{sim.version}"
        )

        print(f"  ✓ Loaded: {sim.name} v{sim.version} ({load_time:.3f}s)")

        # Create executor for notebook-based simulations
        from sim2l.executor import NotebookExecutor
        executor = NotebookExecutor(cache=True, register_results=True)
        print(f"  ✓ Created NotebookExecutor with caching and results registration enabled")

        # Test cases
        test_cases = [
            {"temperature": 300, "power": 10, "iterations": 200, "grid_size": 30, "label": "Low temp, low power"},
            {"temperature": 350, "power": 20, "iterations": 200, "grid_size": 30, "label": "Medium temp, high power"},
            {"temperature": 300, "power": 10, "iterations": 200, "grid_size": 30, "label": "Repeat #1 (cache hit)"},
            {"temperature": 400, "power": 15, "iterations": 300, "grid_size": 40, "label": "High temp, large grid"},
            {"temperature": 350, "power": 20, "iterations": 200, "grid_size": 30, "label": "Repeat #2 (cache hit)"},
        ]

        results = []

        for i, params in enumerate(test_cases, 1):
            label = params.pop('label')
            print(f"\n{'─'*70}")
            print(f"Test Case {i}/{len(test_cases)}: {label}")
            print(f"{'─'*70}")

            print("Parameters:")
            for key, value in params.items():
                print(f"  {key}: {value}")

            # Compute SQUID ID for this execution
            from sim2l.utils import compute_squid_id
            squid_id = compute_squid_id(sim.name, sim.version, params)

            # Check cache service first
            print("\nChecking cache...")
            cache_check_start = time.time()
            try:
                cache_response = requests.get(
                    f"http://localhost:8001/cache/{squid_id}",
                    headers={'X-Session-ID': self.demo_session_id}
                )
                cache_check_time = (time.time() - cache_check_start) * 1000

                if cache_response.status_code == 200:
                    # Cache hit!
                    cached_data = cache_response.json()
                    exec_time = cache_check_time / 1000
                    cache_hit = True

                    # Reconstruct result from cache metadata
                    import types
                    result = types.SimpleNamespace()
                    result.outputs = types.SimpleNamespace()

                    # Extract outputs from metadata field
                    metadata = cached_data.get('metadata', {})
                    outputs = metadata.get('outputs', {})
                    for key, value in outputs.items():
                        setattr(result.outputs, key, value)

                    self.log_interaction(
                        "cache", f"Check Cache for Run #{i}", "success",
                        cache_check_time, f"CACHE HIT for {squid_id[:40]}..."
                    )
                    print(f"  ✓ Cache hit! Retrieved in {exec_time:.3f}s")
                else:
                    cache_hit = False
                    self.log_interaction(
                        "cache", f"Check Cache for Run #{i}", "success",
                        cache_check_time, f"CACHE MISS (status {cache_response.status_code}) for {squid_id[:40]}..."
                    )
                    print(f"  ✗ Cache miss (status {cache_response.status_code}), executing simulation...")
            except Exception as e:
                cache_hit = False
                print(f"  ✗ Cache check failed: {e}, executing simulation...")

            # Execute if not cached
            if not cache_hit:
                print("\nExecuting...")
                exec_start = time.time()

                try:
                    result = sim.run(**params, executor=executor)
                    exec_time = time.time() - exec_start

                    # Check if execution was successful
                    if result is None or not hasattr(result, 'outputs') or result.outputs is None:
                        raise ValueError("Execution failed - no outputs returned")

                    # Store in cache service
                    print("  Storing in cache...")
                    cache_store_start = time.time()

                    # Convert outputs to serializable format (handle Pint quantities)
                    def to_value(val):
                        """Extract numeric value from Pint quantity or return as-is"""
                        if hasattr(val, 'magnitude'):
                            return float(val.magnitude)
                        return float(val) if isinstance(val, (int, float)) else val

                    outputs_data = {
                        'max_temperature': to_value(result.outputs.max_temperature),
                        'avg_temperature': to_value(result.outputs.avg_temperature),
                        'converged': bool(result.outputs.converged),
                        'iterations_to_convergence': int(result.outputs.iterations_to_convergence)
                    }

                    # Compute input hash for cache key
                    import hashlib
                    import json
                    input_hash = hashlib.sha256(
                        json.dumps(params, sort_keys=True).encode()
                    ).hexdigest()

                    # Build cache entry with all required fields
                    cache_data = {
                        'cache_key': squid_id,
                        'simulation_id': sim.id if hasattr(sim, 'id') else 0,
                        'simulation_name': sim.name,
                        'simulation_version': sim.version,
                        'execution_id': squid_id,
                        'squid_id': squid_id,
                        'input_hash': input_hash,
                        'run_db_path': '',  # Not using run database in this demo
                        'metadata': {
                            'inputs': params,
                            'outputs': outputs_data
                        }
                    }

                    cache_store_response = requests.post(
                        "http://localhost:8001/cache",
                        json=cache_data,
                        headers={'X-Session-ID': self.demo_session_id}
                    )
                    cache_store_time = (time.time() - cache_store_start) * 1000

                    if cache_store_response.status_code in [200, 201]:
                        self.log_interaction(
                            "cache", f"Store Result #{i}", "success",
                            cache_store_time, f"Stored {squid_id[:40]}..."
                        )
                        print(f"  ✓ Stored in cache ({cache_store_time:.1f}ms)")
                    else:
                        try:
                            error_json = cache_store_response.json()
                            error_msg = str(error_json)
                        except:
                            error_msg = cache_store_response.text[:200] if cache_store_response.text else str(cache_store_response.status_code)

                        self.log_interaction(
                            "cache", f"Store Result #{i}", "failed",
                            cache_store_time, f"Failed: {cache_store_response.status_code}"
                        )
                        print(f"  ✗ Cache store failed: {cache_store_response.status_code}")
                        if len(error_msg) < 200:
                            print(f"    Error: {error_msg}")

                    # Note: Results are automatically registered by NotebookExecutor

                except Exception as exec_error:
                    raise exec_error

            # Log execution
            self.log_interaction(
                "execution", f"Run #{i}", "success",
                exec_time * 1000,
                f"{'CACHED' if cache_hit else 'NEW'} | Max T: {result.outputs.max_temperature:.2f}K"
            )

            # Store result info
            result_info = {
                'run_number': i,
                'parameters': params.copy(),
                'outputs': {
                    'max_temperature': result.outputs.max_temperature,
                    'avg_temperature': result.outputs.avg_temperature,
                    'converged': result.outputs.converged,
                    'iterations_to_convergence': result.outputs.iterations_to_convergence
                },
                'execution_time': exec_time,
                'cached': cache_hit,
                'squid_id': squid_id
            }

            results.append(result_info)

            # Print results
            print(f"\nResults:")
            print(f"  Status: {'CACHE HIT ⚡' if cache_hit else 'NEW RUN'}")
            print(f"  Execution time: {exec_time:.3f}s")
            print(f"  Max temperature: {result.outputs.max_temperature:.2f} K")
            print(f"  Avg temperature: {result.outputs.avg_temperature:.2f} K")
            print(f"  Converged: {result.outputs.converged}")
            print(f"  Iterations: {result.outputs.iterations_to_convergence}")

        # Summary
        cache_hits = sum(1 for r in results if r['cached'])
        new_runs = len(results) - cache_hits

        print(f"\n{'='*70}")
        print("EXECUTION SUMMARY")
        print(f"{'='*70}")
        print(f"Total runs: {len(results)}")
        print(f"Cache hits: {cache_hits}")
        print(f"New executions: {new_runs}")

        self.log_timeline("Execution Complete", f"{len(results)} simulations executed ({cache_hits} cached)")

        return results

    def explore_cache_database(self):
        """Explore cache database with detailed logging"""
        print("\n" + "="*70)
        print("EXPLORING CACHE DATABASE")
        print("="*70)

        self.log_timeline("Cache Exploration", "Querying cache database for statistics")

        try:
            cache_client = CacheClient(service_url="http://localhost:8001")

            print("\nQuerying cache statistics...")
            start = time.time()
            response = requests.get("http://localhost:8001/cache/stats")
            query_time = time.time() - start

            if response.status_code == 200:
                stats = response.json()
                self.log_interaction(
                    "cache", "Get Statistics", "success",
                    query_time * 1000, f"{stats.get('total_entries', 0)} entries"
                )

                print(f"  ✓ Query successful ({query_time:.3f}s)")
                print(f"\nCache Statistics:")
                print(f"  Total cached entries: {stats.get('total_entries', 0)}")
                print(f"  Total size: {stats.get('total_size', 0)} bytes")

                return stats
            else:
                self.log_interaction(
                    "cache", "Get Statistics", "failed",
                    query_time * 1000, f"HTTP {response.status_code}"
                )
                return {}

        except Exception as e:
            self.log_interaction(
                "cache", "Get Statistics", "failed",
                0, f"Error: {str(e)}"
            )
            print(f"  ✗ Cache query failed: {e}")
            return {}

    def explore_results_database(self):
        """Explore results database with detailed logging"""
        print("\n" + "="*70)
        print("EXPLORING RESULTS DATABASE")
        print("="*70)

        self.log_timeline("Results Exploration", "Querying results database")

        try:
            results_client = ResultsClient(base_url="http://localhost:8003")

            # Search for results
            print("\nSearching for simulation results...")
            start = time.time()
            search_results = results_client.search(
                simulation_name="thermal_analysis",
                limit=10
            )
            query_time = time.time() - start

            self.log_interaction(
                "results", "Search Results", "success",
                query_time * 1000, f"Found {len(search_results)} results"
            )

            print(f"  ✓ Found {len(search_results)} simulation results ({query_time:.3f}s)")

            # Get parameter statistics
            print("\nGetting parameter statistics...")
            # Get statistics for key output parameters
            param_stats = {}
            for param_name in ['max_temperature', 'avg_temperature']:
                try:
                    start = time.time()
                    stats = results_client.get_parameter_stats(
                        "thermal_analysis",
                        param_name,
                        param_class='output'
                    )
                    stats_time = time.time() - start
                    param_stats[param_name] = stats

                    self.log_interaction(
                        "results", f"Get Stats for {param_name}", "success",
                        stats_time * 1000, f"min={stats.get('min')}, max={stats.get('max')}"
                    )
                except Exception as e:
                    print(f"  Warning: Could not get stats for {param_name}: {e}")

            if param_stats:
                print(f"  ✓ Retrieved statistics for {len(param_stats)} parameters")
                print("\nParameter Statistics:")
                for param_name, stats in param_stats.items():
                    print(f"  {param_name}:")
                    print(f"    Range: {stats.get('min', 'N/A')} - {stats.get('max', 'N/A')}")
                    if stats.get('avg'):
                        print(f"    Average: {stats.get('avg'):.2f}")
                    print(f"    Count: {stats.get('count', 0)}")

            return {
                'results': {
                    'count': len(search_results),
                    'sample': search_results[0] if search_results else {}
                },
                'param_stats': param_stats
            }

        except Exception as e:
            self.log_interaction(
                "results", "Query Database", "failed",
                0, f"Error: {str(e)}"
            )
            print(f"  ✗ Results query failed: {e}")
            return {}

    def generate_report(self, service_status, deployment, results, cache_stats, db_results):
        """Generate comprehensive HTML report"""
        print("\n" + "="*70)
        print("GENERATING HTML REPORT")
        print("="*70)

        self.log_timeline("Report Generation", "Creating comprehensive HTML report")

        # Add all sections to report
        self.report.add_service_status(service_status)
        self.report.add_deployment_info(deployment)
        self.report.add_execution_results(results)

        # Calculate cache statistics
        total_runs = len(results)
        cache_hits = sum(1 for r in results if r['cached'])
        new_runs = [r for r in results if not r['cached']]
        cached_runs = [r for r in results if r['cached']]

        avg_new_time = sum(r['execution_time'] for r in new_runs) / len(new_runs) if new_runs else 0
        avg_cached_time = sum(r['execution_time'] for r in cached_runs) / len(cached_runs) if cached_runs else 0

        cache_stats_full = {
            'total_runs': total_runs,
            'cache_hits': cache_hits,
            'total_entries': cache_stats.get('total_entries', 0),
            'total_size': cache_stats.get('total_size', 0),
            'avg_speedup': avg_new_time / avg_cached_time if avg_cached_time > 0 else 0
        }

        self.report.add_cache_statistics(cache_stats_full)
        self.report.add_database_queries(db_results)

        # Performance analysis
        performance = {
            'avg_new_time': avg_new_time,
            'avg_cached_time': avg_cached_time,
            'speedup': avg_new_time / avg_cached_time if avg_cached_time > 0 else 0,
            'time_saved': avg_new_time * cache_hits - avg_cached_time * cache_hits if cache_hits > 0 else 0,
            'timeline': self.timeline_events
        }

        self.report.add_performance_analysis(performance)
        self.report.add_service_interactions(self.service_interactions)

        # Generate HTML file
        output_path = self.report.generate()

        print(f"\n✓ HTML report generated successfully!")
        print(f"  Location: {output_path}")
        print(f"  Size: {output_path.stat().st_size} bytes")

        self.log_timeline("Report Complete", f"Saved to {output_path.name}")

        return output_path

    def stop_services(self):
        """Stop all services"""
        print("\n" + "="*70)
        print("STOPPING SERVICES")
        print("="*70)

        for name, proc in self.processes.items():
            print(f"Stopping {name.upper()} service...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
                print(f"  ✓ {name.upper()} stopped")
                self.log_interaction(name, "Service Shutdown", "success", 0, "Clean shutdown")
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"  ✓ {name.upper()} killed")
                self.log_interaction(name, "Service Shutdown", "success", 0, "Forced shutdown")

        self.processes.clear()
        print("\n✓ All services stopped")

    def run(self):
        """Execute complete workflow"""
        print("\n" + "="*70)
        print("SIM2L COMPLETE WORKFLOW WITH HTML REPORT")
        print("="*70)
        print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # Start services
            service_status = self.start_services()

            # Configure sim2l
            sim2l.configure(
                cache_service_url="http://localhost:8001",
                catalog_service_url="http://localhost:8002"
            )

            # Deploy simulation
            deployment = self.deploy_simulation()

            # Run simulations
            results = self.run_simulations()

            # Explore databases
            cache_stats = self.explore_cache_database()
            db_results = self.explore_results_database()

            # Generate report
            report_path = self.generate_report(
                service_status, deployment, results,
                cache_stats, db_results
            )

            # Final summary
            elapsed = time.time() - self.start_time
            print("\n" + "="*70)
            print("WORKFLOW COMPLETE")
            print("="*70)
            print(f"\n✓ Total time: {elapsed:.2f}s")
            print(f"✓ Service interactions: {len(self.service_interactions)}")
            print(f"✓ Simulations executed: {len(results)}")
            print(f"✓ HTML report: {report_path}")
            print(f"\nOpen the report in your browser:")
            print(f"  file://{report_path}")

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")

        except Exception as e:
            print(f"\n✗ Error during workflow: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # Always stop services
            self.stop_services()

            print("\n" + "="*70)
            print("Thank you for using sim2l!")
            print("="*70)


if __name__ == "__main__":
    runner = VerboseWorkflowRunner()
    runner.run()
