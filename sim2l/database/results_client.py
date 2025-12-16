"""
Results Client for sim2l.

Client for interacting with the Results Service, which stores
introspected simulation results with searchable parameters.
"""

import logging
from typing import Dict, List, Optional, Any
import requests


logger = logging.getLogger(__name__)


class ResultsClient:
    """
    Client for the sim2l Results Service.

    The Results Service introspects simulation runs and stores parameter
    values in a searchable database, enabling powerful queries like:
    - Find all runs where temperature > 300
    - Get statistics for an output parameter across runs
    - Search by combinations of input/output values

    Usage:
        client = ResultsClient(
            "http://localhost:8003",
            session_id=session.session_id
        )

        # Register a result
        client.register_result("exec-2024-001")

        # Search for results
        results = client.search(
            simulation_name="thermal_sim",
            input_filters={'temperature': 350},
            output_filters={'max_stress': {'$gt': 100}}
        )

        # Get parameter statistics
        stats = client.get_parameter_stats(
            "thermal_sim",
            "max_stress",
            param_class="output"
        )
    """

    def __init__(
        self,
        base_url: str,
        session_id: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize the Results Client.

        Args:
            base_url: Base URL of the results service
            session_id: Session ID for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.session_id = session_id
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        """Get request headers with session ID."""
        headers = {'Content-Type': 'application/json'}
        if self.session_id:
            headers['X-Session-ID'] = self.session_id
        return headers

    def health_check(self) -> Dict[str, Any]:
        """
        Check service health.

        Returns:
            Dict with health status
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Health check failed: {e}")
            return {'status': 'unhealthy', 'error': str(e)}

    def register_result(
        self,
        execution_id: str,
        squid_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Register a simulation result.

        This introspects the run database and extracts parameter schemas
        and values for searchable storage.

        Args:
            execution_id: Execution ID of the run to register
            squid_id: Optional SQUID identifier
            metadata: Optional additional metadata

        Returns:
            Dict with result_id and schema_id

        Example:
            result = client.register_result("exec-2024-001")
            print(f"Registered as result ID: {result['result_id']}")
        """
        try:
            response = requests.post(
                f"{self.base_url}/register",
                json={
                    'execution_id': execution_id,
                    'squid_id': squid_id,
                    'metadata': metadata
                },
                headers=self._headers(),
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to register result: {e}")
            raise

    def search(
        self,
        simulation_name: Optional[str] = None,
        input_filters: Optional[Dict[str, Any]] = None,
        output_filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search for results by parameter values.

        Args:
            simulation_name: Filter by simulation name
            input_filters: Dict of input parameter filters
            output_filters: Dict of output parameter filters
            limit: Maximum number of results

        Returns:
            List of matching results

        Example:
            # Find runs with specific input values
            results = client.search(
                simulation_name="thermal_sim",
                input_filters={'temperature': 350, 'pressure': 100}
            )

            # Find runs with output in range (requires PostgreSQL)
            results = client.search(
                simulation_name="thermal_sim",
                output_filters={'max_stress': 150}
            )
        """
        try:
            response = requests.post(
                f"{self.base_url}/search",
                json={
                    'simulation_name': simulation_name,
                    'input_filters': input_filters or {},
                    'output_filters': output_filters or {},
                    'limit': limit
                },
                headers=self._headers(),
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.RequestException as e:
            logger.error(f"Search failed: {e}")
            raise

    def get_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific result by execution ID.

        Args:
            execution_id: Execution ID

        Returns:
            Result dict or None if not found

        Example:
            result = client.get_result("exec-2024-001")
            print(f"Inputs: {result['input_params']}")
            print(f"Outputs: {result['output_params']}")
        """
        try:
            response = requests.get(
                f"{self.base_url}/results/{execution_id}",
                headers=self._headers(),
                timeout=self.timeout
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get result: {e}")
            raise

    def get_parameter_stats(
        self,
        simulation_name: str,
        param_name: str,
        param_class: str = 'output'
    ) -> Dict[str, Any]:
        """
        Get statistics for a parameter across all runs.

        Args:
            simulation_name: Simulation name
            param_name: Parameter name
            param_class: 'input' or 'output'

        Returns:
            Dict with min, max, avg, count

        Example:
            stats = client.get_parameter_stats(
                "thermal_sim",
                "max_stress",
                param_class="output"
            )
            print(f"Average: {stats['avg_value']}")
            print(f"Range: {stats['min_value']} - {stats['max_value']}")
        """
        try:
            response = requests.get(
                f"{self.base_url}/stats/{simulation_name}/{param_name}",
                params={'class': param_class},
                headers=self._headers(),
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get parameter stats: {e}")
            raise

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        return False
