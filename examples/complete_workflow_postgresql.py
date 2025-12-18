#!/usr/bin/env python3
"""
Complete Sim2l Workflow Example with PostgreSQL Backend

This example demonstrates the full sim2l workflow using PostgreSQL for all services:
- Cache Service with PostgreSQL
- Catalog Service with PostgreSQL
- Results Service with PostgreSQL

Prerequisites:
1. PostgreSQL running (use Docker: cd examples && docker-compose up -d)
2. Python packages: psycopg2-binary

Features:
- All services backed by PostgreSQL
- Detailed logging of every service interaction
- HTML report with visualizations
- Service health monitoring
- Performance metrics
- Database query results with full outputs
- Cache statistics

Usage:
    # Start PostgreSQL
    cd examples
    docker-compose up -d

    # Run workflow
    python examples/complete_workflow_postgresql.py

    # Stop PostgreSQL
    docker-compose down
"""

import os
import sys
import time
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


# PostgreSQL connection configuration
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'sim2l')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'sim2l_dev_password')

# Database URLs
CACHE_DB_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/sim2l_cache"
CATALOG_DB_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/sim2l_catalog"
RESULTS_DB_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/sim2l_results"


class PostgreSQLWorkflowRunner:
    """
    Runs complete sim2l workflow with PostgreSQL backend
    """

    def __init__(self):
        self.report = HTMLReportGenerator("sim2l_postgresql_workflow_report.html")
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

    def check_postgres_connection(self):
        """Check if PostgreSQL is accessible"""
        print("\n" + "="*70)
        print("CHECKING POSTGRESQL CONNECTION")
        print("="*70)

        try:
            import psycopg2

            print(f"\nConnecting to PostgreSQL...")
            print(f"  Host: {POSTGRES_HOST}")
            print(f"  Port: {POSTGRES_PORT}")
            print(f"  User: {POSTGRES_USER}")

            # Test connection
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database='postgres'
            )
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            conn.close()

            print(f"  ✓ PostgreSQL connection successful")
            print(f"  Version: {version.split(',')[0]}")

            # Check if databases exist
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database='postgres'
            )
            cursor = conn.cursor()
            cursor.execute("""
                SELECT datname FROM pg_database
                WHERE datname IN ('sim2l_cache', 'sim2l_catalog', 'sim2l_results')
                ORDER BY datname
            """)
            databases = [row[0] for row in cursor.fetchall()]
            conn.close()

            print(f"\n  Databases found:")
            for db in ['sim2l_cache', 'sim2l_catalog', 'sim2l_results']:
                if db in databases:
                    print(f"    ✓ {db}")
                else:
                    print(f"    ✗ {db} (missing)")
                    raise RuntimeError(f"Database {db} not found. Run: docker-compose up -d")

            self.log_timeline("PostgreSQL Check", "Connected to PostgreSQL successfully")
            return True

        except ImportError:
            print("\n  ✗ psycopg2 not installed")
            print("    Install with: pip install psycopg2-binary")
            return False
        except Exception as e:
            print(f"\n  ✗ Failed to connect to PostgreSQL: {e}")
            print("\n  To start PostgreSQL with Docker:")
            print("    cd examples")
            print("    docker-compose up -d")
            return False

    def check_service_health(self, name: str, port: int, url: str) -> Dict[str, Any]:
        """Check service health with detailed logging"""
        print(f"\n  Checking {name.upper()} service health...")

        start = time.time()
        try:
            response = requests.get(f"{url}/health", timeout=5)
            response_time = (time.time() - start) * 1000

            if response.status_code == 200:
                health_data = response.json()
                backend = health_data.get('backend', 'unknown')
                self.log_interaction(
                    name, "Health Check", "success",
                    response_time, f"Status: {health_data.get('status', 'unknown')}, Backend: {backend}"
                )
                return {
                    'healthy': True,
                    'port': port,
                    'url': url,
                    'backend': backend,
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
        """Start all services with PostgreSQL backend"""
        print("\n" + "="*70)
        print("STARTING SIM2L SERVICES (PostgreSQL Backend)")
        print("="*70)

        self.log_timeline("Service Startup", "Beginning service initialization with PostgreSQL")

        services_config = {
            'cache': {
                'module': 'sim2l.services.cache_service',
                'port': 8001,
                'url': "http://localhost:8001",
                'backend': 'postgresql',
                'args': ['--backend', 'postgresql', '--db-url', CACHE_DB_URL, '--no-auth', '--debug']
            },
            'catalog': {
                'module': 'sim2l.services.catalog_service',
                'port': 8002,
                'url': "http://localhost:8002",
                'backend': 'sqlite',  # Catalog doesn't have PostgreSQL backend yet
                'args': ['--debug']  # Uses default SQLite backend with debug logging
            },
            'results': {
                'module': 'sim2l.services.results_service',
                'port': 8003,
                'url': "http://localhost:8003",
                'backend': 'postgresql',
                'args': ['--backend', 'postgresql', '--db-url', RESULTS_DB_URL, '--no-auth', '--debug']
            },
        }

        service_status = {}

        for name, config in services_config.items():
            print(f"\nStarting {name.upper()} service...")
            print(f"  Module: {config['module']}")
            print(f"  Port: {config['port']}")
            print(f"  URL: {config['url']}")
            print(f"  Backend: {config['backend']}")

            start = time.time()

            # Start service with PostgreSQL backend
            cmd = [sys.executable, '-m', config['module']] + config['args']

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, 'FLASK_ENV': 'development'}
            )
            self.processes[name] = proc

            # Wait for service to be ready
            print(f"  Waiting for service to be ready...")
            ready = self.wait_for_service(config['port'], config['url'])

            startup_time = time.time() - start

            if ready:
                status = self.check_service_health(name, config['port'], config['url'])
                service_status[name] = status
                self.log_interaction(
                    name, "Service Startup", "success",
                    startup_time * 1000, f"Ready in {startup_time:.2f}s ({config['backend']})"
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

        self.log_timeline("Services Started", f"All {len(services_config)} services operational with PostgreSQL")
        print("\n✓ All services started successfully with PostgreSQL backend!")

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

        if not notebook_path.exists():
            print(f"\n✗ Notebook not found: {notebook_path}")
            raise FileNotFoundError(f"Notebook not found: {notebook_path}")

        print(f"\nNotebook: {notebook_path.name}")
        print(f"  Path: {notebook_path}")

        start = time.time()

        try:
            # Deploy to catalog service
            sim_id = sim2l.deploy_simulation(
                notebook=str(notebook_path),
                name="thermal_analysis",
                version="1.0.0",
                description="2D thermal analysis with heat source simulation (PostgreSQL)",
                author="Sim2l Team"
            )

            deploy_time = time.time() - start

            deployment_info = {
                'sim_id': sim_id,
                'name': "thermal_analysis",
                'version': "1.0.0",
                'notebook': str(notebook_path.name),
                'description': "2D thermal analysis with heat source simulation (PostgreSQL)",
                'author': "Sim2l Team",
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            self.log_interaction(
                "catalog", "Deploy Simulation", "success",
                deploy_time * 1000, f"Simulation ID: {sim_id}"
            )

            print(f"  ✓ Deployed successfully (ID: {sim_id})")
            print(f"  ✓ Deployment time: {deploy_time:.2f}s")

            self.log_timeline("Deployment Complete", f"thermal_analysis v1.0.0 ready")

            return deployment_info

        except ValueError as e:
            if "already exists" in str(e):
                print(f"\nℹ Simulation already exists in catalog, loading it instead...")
                sim = sim2l.load_simulation("thermal_analysis")
                sim_id = sim.id if hasattr(sim, 'id') else 0
                deploy_time = time.time() - start

                deployment_info = {
                    'sim_id': sim_id,
                    'name': "thermal_analysis",
                    'version': "1.0.0",
                    'notebook': str(notebook_path.name),
                    'description': "2D thermal analysis with heat source simulation (PostgreSQL, existing)",
                    'author': "Sim2l Team",
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                self.log_interaction(
                    "catalog", "Load Existing Simulation", "success",
                    deploy_time * 1000, f"Loaded thermal_analysis"
                )

                print(f"  ✓ Using existing simulation (already deployed)")
                return deployment_info
            else:
                deploy_time = time.time() - start
                self.log_interaction(
                    "catalog", "Deploy Simulation", "failed",
                    deploy_time * 1000, str(e)
                )
                raise

    def run_simulations(self) -> List[Dict[str, Any]]:
        """Run multiple simulations with different parameters"""
        print("\n" + "="*70)
        print("RUNNING SIMULATIONS")
        print("="*70)

        self.log_timeline("Simulation Execution", "Running parametric study")

        # Load simulation
        sim = sim2l.load_simulation("thermal_analysis")

        # Configure sim2l to use services
        sim2l.configure(
            cache_service_url="http://localhost:8001",
            catalog_service_url="http://localhost:8002",
            results_service_url="http://localhost:8003",
            debug_mode=True  # Enable DEBUG logging
        )

        # Create executor with results registration enabled
        from sim2l.executor import NotebookExecutor
        executor = NotebookExecutor(cache=True, register_results=True)
        print(f"  ✓ Created NotebookExecutor with caching and results registration enabled")

        # Test cases
        test_cases = [
            {"temperature": 300, "power": 10, "grid_size": 30, "iterations": 200},
            {"temperature": 350, "power": 20, "grid_size": 30, "iterations": 200},
            {"temperature": 300, "power": 10, "grid_size": 30, "iterations": 200},  # Cache hit
            {"temperature": 400, "power": 15, "grid_size": 40, "iterations": 300},
            {"temperature": 350, "power": 20, "grid_size": 30, "iterations": 200},  # Cache hit
        ]

        results = []
        cache_hits = 0

        print(f"\nExecuting {len(test_cases)} test cases...")
        print("")

        for i, params in enumerate(test_cases, 1):
            print(f"Test Case {i}: T={params['temperature']}K, P={params['power']}W, "
                  f"Grid={params['grid_size']}x{params['grid_size']}, Iter={params['iterations']}")

            start = time.time()
            result = sim.run(**params, executor=executor)
            exec_time = time.time() - start

            cached = result.status == "completed" and exec_time < 1.0
            if cached:
                cache_hits += 1

            status = "success" if result.status == "completed" else "failed"
            cache_status = "CACHE HIT ⚡" if cached else "NEW RUN"

            self.log_interaction(
                "executor", f"Run Test Case {i}", status,
                exec_time * 1000, cache_status
            )

            result_info = {
                'run_number': i,
                'parameters': params.copy(),
                'outputs': {
                    'max_temperature': result.outputs.max_temperature if result.outputs else None,
                    'avg_temperature': result.outputs.avg_temperature if result.outputs else None,
                    'converged': result.outputs.converged if result.outputs else False,
                    'iterations_to_convergence': result.outputs.iterations_to_convergence if result.outputs else 0
                },
                'execution_time': exec_time,
                'cached': cached,
                'squid_id': result.squid_id if (hasattr(result, 'squid_id') and result.squid_id) else 'N/A'
            }

            results.append(result_info)

            print(f"  ✓ {cache_status} - Completed in {exec_time:.2f}s")
            if result.outputs:
                print(f"    Max T: {result.outputs.max_temperature}")
                print(f"    Avg T: {result.outputs.avg_temperature}")
                print(f"    Converged: {result.outputs.converged}")
            print("")

        self.execution_results = results

        print(f"Cache hits: {cache_hits}")
        print(f"New executions: {len(test_cases) - cache_hits}")

        self.log_timeline("Simulations Complete", f"{len(test_cases)} runs finished, {cache_hits} cache hits")

        return results

    def explore_cache_database(self):
        """Query cache database statistics"""
        print("\n" + "="*70)
        print("EXPLORING CACHE DATABASE (PostgreSQL)")
        print("="*70)

        self.log_timeline("Cache Exploration", "Querying cache database for statistics")

        try:
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
                print(f"  ✗ Query failed: HTTP {response.status_code}")
                return {}

        except Exception as e:
            query_time = time.time() - start
            self.log_interaction(
                "cache", "Get Statistics", "failed",
                query_time * 1000, str(e)
            )
            print(f"  ✗ Query failed: {e}")
            return {}

    def explore_results_database(self):
        """Query results database"""
        print("\n" + "="*70)
        print("EXPLORING RESULTS DATABASE (PostgreSQL)")
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
            param_stats = {}
            for param_name in ['max_temperature', 'avg_temperature']:
                try:
                    start = time.time()
                    stats = results_client.get_parameter_stats(
                        "thermal_analysis",
                        param_name,
                        param_class="output"
                    )
                    stats_time = time.time() - start

                    param_stats[param_name] = stats

                    self.log_interaction(
                        "results", f"Get Stats for {param_name}", "success",
                        stats_time * 1000, f"min={stats.get('min_value')}, max={stats.get('max_value')}"
                    )

                except Exception as e:
                    print(f"  Warning: Could not get stats for {param_name}: {e}")

            if param_stats:
                print(f"  ✓ Retrieved statistics for {len(param_stats)} parameters")
                print("\nParameter Statistics:")
                for param_name, stats in param_stats.items():
                    print(f"  {param_name}:")
                    print(f"    Range: {stats.get('min_value', 'N/A')} - {stats.get('max_value', 'N/A')}")
                    if stats.get('avg_value'):
                        print(f"    Average: {stats.get('avg_value'):.2f}")
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
        """Stop all services gracefully"""
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
                print(f"  ⚠ {name.upper()} killed (timeout)")
                self.log_interaction(name, "Service Shutdown", "failed", 0, "Forced kill")

        print("\n✓ All services stopped")

    def run(self):
        """Execute complete workflow"""
        print("\n" + "="*70)
        print("SIM2L COMPLETE WORKFLOW WITH POSTGRESQL")
        print("="*70)
        print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # Check PostgreSQL connection
            if not self.check_postgres_connection():
                return

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

            # Explore cache database
            cache_stats = self.explore_cache_database()

            # Explore results database
            db_results = self.explore_results_database()

            # Generate report
            report_path = self.generate_report(service_status, deployment, results, cache_stats, db_results)

            # Print summary
            print("\n" + "="*70)
            print("WORKFLOW COMPLETE")
            print("="*70)
            print(f"\n✓ Total time: {time.time() - self.start_time:.2f}s")
            print(f"✓ Service interactions: {len(self.service_interactions)}")
            print(f"✓ Simulations executed: {len(self.execution_results)}")
            print(f"✓ Backend: PostgreSQL")
            print(f"✓ HTML report: {report_path}")
            print(f"\nOpen the report in your browser:")
            print(f"  file://{Path(report_path).resolve()}")

        finally:
            self.stop_services()

        print("\n" + "="*70)
        print("Thank you for using sim2l with PostgreSQL!")
        print("="*70)


if __name__ == "__main__":
    runner = PostgreSQLWorkflowRunner()
    runner.run()
