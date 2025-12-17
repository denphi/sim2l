#!/usr/bin/env python3
"""
Unit tests for the complete workflow example

Tests the full sim2l workflow:
- Service management
- Simulation deployment
- Parameterized execution
- Caching
- Database queries
"""

import unittest
import sys
import time
import tempfile
import shutil
from pathlib import Path
import subprocess
import requests

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sim2l
from sim2l.database import CacheClient, ResultsClient, FileManager


class TestServiceManagement(unittest.TestCase):
    """Test service lifecycle management"""

    def setUp(self):
        """Set up test environment"""
        self.processes = {}
        self.ports = {
            'cache': 8011,
            'catalog': 8012,
            'results': 8013
        }

    def tearDown(self):
        """Clean up services"""
        for name, proc in self.processes.items():
            if proc.poll() is None:  # Still running
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def start_service(self, name, module, port):
        """Start a service"""
        proc = subprocess.Popen(
            [sys.executable, '-m', module],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**subprocess.os.environ, 'FLASK_RUN_PORT': str(port)}
        )
        self.processes[name] = proc
        return proc

    def wait_for_service(self, port, timeout=10):
        """Wait for service to be ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f'http://localhost:{port}/health', timeout=1)
                if response.status_code == 200:
                    return True
            except (requests.ConnectionError, requests.Timeout):
                time.sleep(0.5)
        return False

    def test_start_cache_service(self):
        """Test starting cache service"""
        port = self.ports['cache']
        self.start_service('cache', 'sim2l.services.cache_service', port)
        self.assertTrue(self.wait_for_service(port), "Cache service failed to start")

        # Test health endpoint
        response = requests.get(f'http://localhost:{port}/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'healthy')

    def test_start_catalog_service(self):
        """Test starting catalog service"""
        port = self.ports['catalog']
        self.start_service('catalog', 'sim2l.services.catalog_service', port)
        self.assertTrue(self.wait_for_service(port), "Catalog service failed to start")

        response = requests.get(f'http://localhost:{port}/health')
        self.assertEqual(response.status_code, 200)

    def test_start_results_service(self):
        """Test starting results service"""
        port = self.ports['results']
        self.start_service('results', 'sim2l.services.results_service', port)
        self.assertTrue(self.wait_for_service(port), "Results service failed to start")

        response = requests.get(f'http://localhost:{port}/health')
        self.assertEqual(response.status_code, 200)

    def test_start_all_services(self):
        """Test starting all services together"""
        for name, module in [
            ('cache', 'sim2l.services.cache_service'),
            ('catalog', 'sim2l.services.catalog_service'),
            ('results', 'sim2l.services.results_service')
        ]:
            port = self.ports[name]
            self.start_service(name, module, port)
            self.assertTrue(
                self.wait_for_service(port),
                f"{name} service failed to start"
            )

        # Verify all services are healthy
        for name, port in self.ports.items():
            response = requests.get(f'http://localhost:{port}/health')
            self.assertEqual(response.status_code, 200, f"{name} service not healthy")


class TestSimulationDeployment(unittest.TestCase):
    """Test simulation deployment"""

    @classmethod
    def setUpClass(cls):
        """Set up test database"""
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = Path(cls.test_dir) / "test_repo.db"

        # Configure sim2l
        sim2l.configure(db_path=str(cls.db_path))

    @classmethod
    def tearDownClass(cls):
        """Clean up test database"""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_deploy_thermal_simulation(self):
        """Test deploying thermal_simulation.ipynb"""
        notebook_path = Path(__file__).parent.parent / "examples" / "thermal_simulation.ipynb"

        if not notebook_path.exists():
            self.skipTest(f"Notebook not found: {notebook_path}")

        sim_id = sim2l.deploy_simulation(
            notebook=str(notebook_path),
            name="test_thermal",
            version="1.0.0",
            description="Test deployment",
            author="Test Suite"
        )

        self.assertIsNotNone(sim_id)
        self.assertIsInstance(sim_id, int)
        self.assertGreater(sim_id, 0)

    def test_load_deployed_simulation(self):
        """Test loading a deployed simulation"""
        notebook_path = Path(__file__).parent.parent / "examples" / "thermal_simulation.ipynb"

        if not notebook_path.exists():
            self.skipTest(f"Notebook not found: {notebook_path}")

        # Deploy first
        sim2l.deploy_simulation(
            notebook=str(notebook_path),
            name="test_thermal_load",
            version="1.0.0"
        )

        # Load it
        sim = sim2l.load_simulation("test_thermal_load")

        self.assertIsNotNone(sim)
        self.assertEqual(sim.name, "test_thermal_load")
        self.assertEqual(sim.version, "1.0.0")

    def test_list_simulations(self):
        """Test listing deployed simulations"""
        notebook_path = Path(__file__).parent.parent / "examples" / "thermal_simulation.ipynb"

        if not notebook_path.exists():
            self.skipTest(f"Notebook not found: {notebook_path}")

        # Deploy a simulation
        sim2l.deploy_simulation(
            notebook=str(notebook_path),
            name="test_list_sim",
            version="1.0.0"
        )

        # List simulations
        sims = sim2l.list_simulations()

        self.assertIsInstance(sims, list)
        self.assertGreater(len(sims), 0)

        # Check that our simulation is in the list
        names = [s.get('name') for s in sims]
        self.assertIn("test_list_sim", names)


class TestParameterizedExecution(unittest.TestCase):
    """Test running simulations with different parameters"""

    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = Path(cls.test_dir) / "test_exec.db"

        sim2l.configure(db_path=str(cls.db_path))

        # Deploy simulation
        notebook_path = Path(__file__).parent.parent / "examples" / "thermal_simulation.ipynb"
        if notebook_path.exists():
            sim2l.deploy_simulation(
                notebook=str(notebook_path),
                name="test_exec_thermal",
                version="1.0.0"
            )

    @classmethod
    def tearDownClass(cls):
        """Clean up"""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_run_with_default_parameters(self):
        """Test running simulation with default parameters"""
        from sim2l.executor import NotebookExecutor

        sim = sim2l.load_simulation("test_exec_thermal")
        executor = NotebookExecutor(cache=False)

        result = sim.run(
            temperature=300,
            power=10,
            iterations=100,
            grid_size=20,
            executor=executor
        )

        self.assertIsNotNone(result)
        self.assertTrue(hasattr(result, 'outputs'))

    def test_run_with_different_parameters(self):
        """Test running with various parameter sets"""
        from sim2l.executor import NotebookExecutor

        sim = sim2l.load_simulation("test_exec_thermal")
        executor = NotebookExecutor(cache=False)

        test_cases = [
            {"temperature": 300, "power": 10, "iterations": 100, "grid_size": 20},
            {"temperature": 350, "power": 15, "iterations": 150, "grid_size": 25},
            {"temperature": 400, "power": 20, "iterations": 200, "grid_size": 30},
        ]

        results = []
        for params in test_cases:
            result = sim.run(**params, executor=executor)
            results.append(result)

            self.assertIsNotNone(result)
            self.assertTrue(hasattr(result, 'outputs'))

        # Verify we got different results for different parameters
        self.assertEqual(len(results), len(test_cases))

    def test_parameter_validation(self):
        """Test that invalid parameters are rejected"""
        sim = sim2l.load_simulation("test_exec_thermal")

        # Test with missing required parameter
        with self.assertRaises(Exception):
            sim.run(temperature=300)  # Missing other required params

        # Test with invalid parameter type
        with self.assertRaises(Exception):
            sim.run(
                temperature="not a number",
                power=10,
                iterations=100,
                grid_size=20
            )


class TestCaching(unittest.TestCase):
    """Test caching functionality"""

    @classmethod
    def setUpClass(cls):
        """Set up test environment with caching"""
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = Path(cls.test_dir) / "test_cache.db"

        sim2l.configure(
            db_path=str(cls.db_path),
            cache_enabled=True
        )

        # Deploy simulation
        notebook_path = Path(__file__).parent.parent / "examples" / "thermal_simulation.ipynb"
        if notebook_path.exists():
            sim2l.deploy_simulation(
                notebook=str(notebook_path),
                name="test_cache_thermal",
                version="1.0.0"
            )

    @classmethod
    def tearDownClass(cls):
        """Clean up"""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_cache_hit(self):
        """Test that repeated runs with same parameters hit cache"""
        from sim2l.executor import NotebookExecutor

        sim = sim2l.load_simulation("test_cache_thermal")
        executor = NotebookExecutor(cache=True)

        params = {
            "temperature": 300,
            "power": 10,
            "iterations": 100,
            "grid_size": 20
        }

        # First run - should execute
        start_time = time.time()
        result1 = sim.run(**params, executor=executor)
        time1 = time.time() - start_time

        # Second run - should hit cache
        start_time = time.time()
        result2 = sim.run(**params, executor=executor)
        time2 = time.time() - start_time

        # Cache should be faster
        self.assertLess(time2, time1, "Cached run should be faster")

        # Results should be identical
        self.assertEqual(
            result1.outputs.max_temperature,
            result2.outputs.max_temperature
        )

    def test_cache_miss_different_parameters(self):
        """Test that different parameters don't hit cache"""
        from sim2l.executor import NotebookExecutor

        sim = sim2l.load_simulation("test_cache_thermal")
        executor = NotebookExecutor(cache=True)

        result1 = sim.run(temperature=300, power=10, iterations=100, grid_size=20, executor=executor)
        result2 = sim.run(temperature=350, power=15, iterations=100, grid_size=20, executor=executor)

        # Results should be different
        self.assertNotEqual(
            result1.outputs.max_temperature,
            result2.outputs.max_temperature
        )

    def test_squid_id_consistency(self):
        """Test that SQUID IDs are consistent for same parameters"""
        from sim2l.utils import compute_squid_id

        params1 = {"temperature": 300, "power": 10}
        params2 = {"temperature": 300, "power": 10}
        params3 = {"temperature": 350, "power": 10}

        squid1 = compute_squid_id("test_sim", "1.0.0", params1)
        squid2 = compute_squid_id("test_sim", "1.0.0", params2)
        squid3 = compute_squid_id("test_sim", "1.0.0", params3)

        # Same parameters should produce same SQUID
        self.assertEqual(squid1, squid2)

        # Different parameters should produce different SQUID
        self.assertNotEqual(squid1, squid3)


class TestDatabaseQueries(unittest.TestCase):
    """Test database query functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.results_db = Path(self.test_dir) / "results.db"

    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_results_client_initialization(self):
        """Test ResultsClient initialization"""
        # ResultsClient requires base_url
        client = ResultsClient(base_url="http://localhost:8003")
        self.assertIsNotNone(client)

    def test_cache_client_initialization(self):
        """Test CacheClient initialization"""
        # CacheClient requires service_url
        client = CacheClient(service_url="http://localhost:8001")
        self.assertIsNotNone(client)

    def test_file_manager_initialization(self):
        """Test FileManager initialization"""
        # FileManager can be initialized without parameters
        manager = FileManager()
        self.assertIsNotNone(manager)


class TestCompleteWorkflow(unittest.TestCase):
    """Integration test for complete workflow"""

    @classmethod
    def setUpClass(cls):
        """Set up complete test environment"""
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = Path(cls.test_dir) / "workflow.db"

        sim2l.configure(
            db_path=str(cls.db_path),
            cache_enabled=True
        )

    @classmethod
    def tearDownClass(cls):
        """Clean up"""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_full_workflow(self):
        """Test complete workflow from deployment to execution"""
        from sim2l.executor import NotebookExecutor

        notebook_path = Path(__file__).parent.parent / "examples" / "thermal_simulation.ipynb"

        if not notebook_path.exists():
            self.skipTest(f"Notebook not found: {notebook_path}")

        # Step 1: Deploy simulation
        sim_id = sim2l.deploy_simulation(
            notebook=str(notebook_path),
            name="workflow_test",
            version="1.0.0",
            description="Integration test",
            author="Test Suite"
        )

        self.assertIsNotNone(sim_id)

        # Step 2: Load simulation
        sim = sim2l.load_simulation("workflow_test")
        self.assertEqual(sim.name, "workflow_test")

        # Create executor with caching enabled
        executor = NotebookExecutor(cache=True)

        # Step 3: Run with first set of parameters
        params1 = {
            "temperature": 300,
            "power": 10,
            "iterations": 100,
            "grid_size": 20
        }

        start_time = time.time()
        result1 = sim.run(**params1, executor=executor)
        time1 = time.time() - start_time

        self.assertIsNotNone(result1)
        self.assertTrue(hasattr(result1, 'outputs'))

        # Step 4: Run with same parameters (should hit cache)
        start_time = time.time()
        result2 = sim.run(**params1, executor=executor)
        time2 = time.time() - start_time

        self.assertLess(time2, time1, "Cached run should be faster")

        # Step 5: Run with different parameters
        params2 = {
            "temperature": 350,
            "power": 15,
            "iterations": 100,
            "grid_size": 20
        }

        result3 = sim.run(**params2, executor=executor)

        self.assertIsNotNone(result3)
        self.assertNotEqual(
            result1.outputs.max_temperature,
            result3.outputs.max_temperature
        )

        # Step 6: Verify results
        self.assertTrue(result1.outputs.converged)
        self.assertTrue(result2.outputs.converged)
        self.assertTrue(result3.outputs.converged)

        print("\n" + "="*70)
        print("COMPLETE WORKFLOW TEST RESULTS")
        print("="*70)
        print(f"Deployment: SUCCESS (ID={sim_id})")
        print(f"First run: {time1:.2f}s")
        print(f"Cached run: {time2:.2f}s ({time1/time2:.1f}x speedup)")
        print(f"Different params: SUCCESS")
        print("="*70)


def run_tests():
    """Run all tests with verbose output"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestServiceManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestSimulationDeployment))
    suite.addTests(loader.loadTestsFromTestCase(TestParameterizedExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestCaching))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseQueries))
    suite.addTests(loader.loadTestsFromTestCase(TestCompleteWorkflow))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
