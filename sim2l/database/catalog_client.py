"""
Master catalog client for simulation registry.

Connects to the central master catalog database with session-based
authentication and automatic sync capabilities.
"""

import requests
import logging
import hashlib
import json
import base64
from typing import Dict, Optional, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


def _default_workflow_entrypoint(workflow_type: str) -> str:
    workflow_type = (workflow_type or "").lower()
    if workflow_type == "notebook":
        return "workflow.ipynb"
    if workflow_type in ("function", "python"):
        return "workflow.py"
    if workflow_type == "docker":
        return "Dockerfile"
    return "workflow.bin"


def _workflow_bundle_from_simulation(sim_def) -> Dict[str, Any]:
    """Build a portable workflow bundle payload from a SimulationDefinition."""
    workflow_bytes = sim_def.get_workflow_bytes()
    entrypoint = _default_workflow_entrypoint(getattr(sim_def, "workflow_type", "notebook"))

    return {
        "format_version": 1,
        "workflow_type": sim_def.workflow_type,
        "entrypoint": entrypoint,
        "files": [
            {
                "path": entrypoint,
                "encoding": "base64",
                "content_base64": base64.b64encode(workflow_bytes).decode("ascii"),
                "size_bytes": len(workflow_bytes),
                "sha256": hashlib.sha256(workflow_bytes).hexdigest(),
            }
        ],
    }


class CatalogClient:
    """
    Client for master catalog service.

    Provides access to the central simulation registry with:
    - Tool/simulation discovery
    - Version management
    - Execution statistics
    - Automatic sync for new installations
    """

    def __init__(
        self,
        service_url: str,
        session_id: Optional[str] = None,
        installation_id: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize catalog client.

        Args:
            service_url: URL of catalog service (e.g., 'http://localhost:8002')
            session_id: Session ID for authentication
            installation_id: Unique installation ID for this client
            timeout: Request timeout in seconds
        """
        self.service_url = service_url.rstrip("/")
        self.session_id = session_id
        self.installation_id = installation_id or self._generate_installation_id()
        self.timeout = timeout
        self._session = requests.Session()

        if session_id:
            self._session.headers.update({"X-Session-ID": session_id})

        # Register installation
        if session_id:
            self._register_installation()

    def _generate_installation_id(self) -> str:
        """Generate a unique installation ID based on hostname."""
        import socket
        import uuid

        hostname = socket.gethostname()
        mac = uuid.getnode()
        installation_str = f"{hostname}:{mac}"
        return hashlib.sha256(installation_str.encode()).hexdigest()[:16]

    def _register_installation(self):
        """Register this installation with the catalog."""
        import platform
        import sys

        try:
            payload = {
                "installation_id": self.installation_id,
                "hostname": platform.node(),
                "platform": platform.system().lower(),
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "sim2l_version": self._get_sim2l_version(),
            }

            response = self._session.post(
                f"{self.service_url}/installations",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code in [200, 201]:
                logger.info(f"Installation {self.installation_id} registered")
            else:
                logger.warning(
                    f"Failed to register installation: {response.status_code}"
                )

        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not register installation: {e}")

    def _get_sim2l_version(self) -> str:
        """Get sim2l version."""
        try:
            from .. import __version__

            return __version__
        except ImportError:
            return "unknown"

    def search(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = "active",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search for simulations in the catalog.

        Args:
            query: Search query (name pattern)
            tags: Filter by tags
            status: 'active', 'deprecated', 'archived', or 'all'
            limit: Maximum number of results

        Returns:
            List of simulation metadata dicts
        """
        try:
            params = {
                "limit": limit,
            }

            if query:
                params["query"] = query
            if tags:
                params["tags"] = ",".join(tags)
            if status != "all":
                params["status"] = status

            response = self._session.get(
                f"{self.service_url}/simulations/search",
                params=params,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Search failed: {response.status_code} {response.text}"
                )
                return []

        except requests.exceptions.RequestException as e:
            logger.error(f"Catalog service request failed: {e}")
            return []

    def get_simulation(
        self, name: str, version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get simulation metadata.

        Args:
            name: Simulation name
            version: Simulation version (None = latest)

        Returns:
            Simulation metadata or None if not found
        """
        try:
            params = {}
            if version:
                params["version"] = version

            response = self._session.get(
                f"{self.service_url}/simulations/{name}",
                params=params,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.debug(f"Simulation {name}/{version} not found in catalog")
                return None
            else:
                logger.error(
                    f"Failed to get simulation: {response.status_code} {response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Catalog service request failed: {e}")
            return None

    def register_simulation(
        self,
        name: str,
        version: str,
        description: Optional[str] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        workflow_type: str = "notebook",
        workflow_hash: Optional[str] = None,
        workflow_bundle: Optional[Dict[str, Any]] = None,
        workflow_files: Optional[List[Dict[str, Any]]] = None,
        workflow_entrypoint: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_approve: bool = False,
    ) -> bool:
        """
        Register a simulation with the catalog.

        This creates a sync request that may require approval based on
        the user's privileges.

        Args:
            name: Simulation name
            version: Simulation version
            description: Description
            author: Author name
            tags: List of tags
            input_schema: Input schema (JSON)
            output_schema: Output schema (JSON)
            workflow_type: 'notebook', 'function', or 'dag'
            workflow_hash: SHA256 hash of workflow
            workflow_bundle: Portable workflow bundle with embedded files
            workflow_files: Convenience alternative to workflow_bundle.files
            workflow_entrypoint: Entrypoint path within workflow bundle/files
            dependencies: List of package dependencies
            metadata: Additional metadata
            auto_approve: Auto-approve if user has privilege (admin only)

        Returns:
            True if registration request submitted successfully
        """
        try:
            payload = {
                "installation_id": self.installation_id,
                "name": name,
                "version": version,
                "description": description,
                "author": author,
                "tags": tags or [],
                "input_schema": input_schema,
                "output_schema": output_schema,
                "workflow_type": workflow_type,
                "workflow_hash": workflow_hash,
                "dependencies": dependencies or [],
                "metadata": metadata,
                "auto_approve": auto_approve,
            }
            if workflow_bundle is not None:
                payload["workflow_bundle"] = workflow_bundle
            if workflow_files is not None:
                payload["workflow_files"] = workflow_files
            if workflow_entrypoint is not None:
                payload["workflow_entrypoint"] = workflow_entrypoint

            response = self._session.post(
                f"{self.service_url}/simulations",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code in [200, 201]:
                logger.info(f"Simulation {name}/{version} registered")
                return True
            elif response.status_code == 202:
                logger.info(
                    f"Simulation {name}/{version} registration pending approval"
                )
                return True
            elif response.status_code == 401:
                logger.error("Unauthorized: Invalid or expired session")
                return False
            else:
                logger.error(
                    f"Registration failed: {response.status_code} {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Catalog service request failed: {e}")
            return False

    def update_simulation(
        self,
        simulation_id: int,
        updates: Dict[str, Any],
    ) -> bool:
        """
        Update simulation metadata.

        Requires appropriate privileges (owner/maintainer/admin).

        Args:
            simulation_id: Simulation ID
            updates: Dict of fields to update

        Returns:
            True if successful
        """
        try:
            response = self._session.patch(
                f"{self.service_url}/simulations/{simulation_id}",
                json=updates,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                logger.info(f"Simulation {simulation_id} updated")
                return True
            elif response.status_code == 401:
                logger.error("Unauthorized: Invalid or expired session")
                return False
            elif response.status_code == 403:
                logger.error("Forbidden: Insufficient privileges")
                return False
            else:
                logger.error(
                    f"Update failed: {response.status_code} {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Catalog service request failed: {e}")
            return False

    def deprecate_simulation(
        self, simulation_id: int, reason: Optional[str] = None
    ) -> bool:
        """
        Mark a simulation as deprecated.

        Args:
            simulation_id: Simulation ID
            reason: Deprecation reason

        Returns:
            True if successful
        """
        return self.update_simulation(
            simulation_id,
            {"status": "deprecated", "metadata": {"deprecation_reason": reason}},
        )

    def record_execution(
        self,
        execution_id: str,
        squid_id: str,
        simulation_id: int,
        started_at: str,
        duration_seconds: Optional[float] = None,
        status: str = "completed",
        executor_type: str = "local",
        cache_hit: bool = False,
        run_db_path: Optional[str] = None,
        input_hash: Optional[str] = None,
        output_count: int = 0,
        artifact_count: int = 0,
        error_count: int = 0,
        warning_count: int = 0,
    ) -> bool:
        """
        Record an execution in the registry.

        Args:
            execution_id: Execution ID
            squid_id: SQUID ID
            simulation_id: Simulation ID
            started_at: Start timestamp (ISO format)
            duration_seconds: Duration
            status: 'running', 'completed', 'failed', 'cached'
            executor_type: 'local', 'notebook', 'remote'
            cache_hit: Whether this was a cache hit
            run_db_path: Path to run database
            input_hash: Hash of inputs
            output_count: Number of outputs
            artifact_count: Number of artifacts
            error_count: Number of errors
            warning_count: Number of warnings

        Returns:
            True if successful
        """
        try:
            payload = {
                "execution_id": execution_id,
                "squid_id": squid_id,
                "simulation_id": simulation_id,
                "started_at": started_at,
                "duration_seconds": duration_seconds,
                "status": status,
                "executor_type": executor_type,
                "cache_hit": cache_hit,
                "run_db_path": run_db_path,
                "input_hash": input_hash,
                "output_count": output_count,
                "artifact_count": artifact_count,
                "error_count": error_count,
                "warning_count": warning_count,
            }

            response = self._session.post(
                f"{self.service_url}/executions",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code in [200, 201]:
                logger.debug(f"Execution {execution_id} recorded in catalog")
                return True
            else:
                logger.warning(
                    f"Failed to record execution: {response.status_code} {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not record execution: {e}")
            return False

    def get_stats(self, simulation_id: int) -> Optional[Dict[str, Any]]:
        """
        Get execution statistics for a simulation.

        Args:
            simulation_id: Simulation ID

        Returns:
            Dict with statistics or None on error
        """
        try:
            response = self._session.get(
                f"{self.service_url}/simulations/{simulation_id}/stats",
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to get stats: {response.status_code} {response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Catalog service request failed: {e}")
            return None

    def sync_local_simulations(
        self, repository_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sync locally installed simulations with the catalog.

        Scans the local repository and submits sync requests for
        any simulations not already in the catalog.

        Args:
            repository_path: Path to local repository database
                (default: ~/.sim2l/simulations.db)

        Returns:
            Dict with sync results
        """
        from ..repository.sqlite import SQLiteBackend

        if repository_path is None:
            repository_path = str(Path.home() / ".sim2l" / "simulations.db")

        results = {
            "scanned": 0,
            "already_registered": 0,
            "sync_requested": 0,
            "errors": 0,
        }

        try:
            # Connect to local repository
            backend = SQLiteBackend(repository_path)

            # Get all active simulations
            local_sims = backend.list(status="active")
            results["scanned"] = len(local_sims)

            for sim in local_sims:
                name = sim["name"]
                version = sim["version"]

                # Check if already in catalog
                catalog_sim = self.get_simulation(name, version)

                if catalog_sim:
                    results["already_registered"] += 1
                    logger.debug(f"Simulation {name}/{version} already in catalog")
                    continue

                input_schema = sim.get("input_schema")
                output_schema = sim.get("output_schema")
                workflow_type = sim.get("workflow_type", "notebook")
                workflow_hash = sim.get("workflow_hash")
                dependencies = sim.get("dependencies", [])
                workflow_bundle = None
                try:
                    sim_def = backend.load(name, version)
                    input_schema = sim_def.inputs.to_dict()
                    output_schema = sim_def.outputs.to_dict()
                    workflow_type = sim_def.workflow_type
                    workflow_hash = sim_def.workflow_hash
                    dependencies = sim_def.dependencies
                    workflow_bundle = _workflow_bundle_from_simulation(sim_def)
                except Exception as exc:
                    logger.warning(
                        "Could not build workflow bundle for %s/%s: %s",
                        name,
                        version,
                        exc,
                    )

                # Submit sync request
                success = self.register_simulation(
                    name=name,
                    version=version,
                    description=sim.get("description"),
                    author=sim.get("author"),
                    tags=sim.get("tags", []),
                    input_schema=input_schema,
                    output_schema=output_schema,
                    workflow_type=workflow_type,
                    workflow_hash=workflow_hash,
                    workflow_bundle=workflow_bundle,
                    dependencies=dependencies,
                )

                if success:
                    results["sync_requested"] += 1
                else:
                    results["errors"] += 1

            logger.info(
                f"Sync completed: {results['sync_requested']} requests submitted, "
                f"{results['already_registered']} already registered, "
                f"{results['errors']} errors"
            )

            return results

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            results["errors"] += 1
            return results

    def get_pending_sync_requests(self) -> List[Dict[str, Any]]:
        """
        Get pending sync requests for this installation.

        Requires appropriate privileges.

        Returns:
            List of pending sync request dicts
        """
        try:
            response = self._session.get(
                f"{self.service_url}/sync/pending",
                params={"installation_id": self.installation_id},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to get pending requests: {response.status_code} {response.text}"
                )
                return []

        except requests.exceptions.RequestException as e:
            logger.error(f"Catalog service request failed: {e}")
            return []

    def approve_sync_request(self, request_id: int) -> bool:
        """
        Approve a sync request.

        Requires admin privileges.

        Args:
            request_id: Sync request ID

        Returns:
            True if successful
        """
        try:
            response = self._session.post(
                f"{self.service_url}/sync/{request_id}/approve",
                timeout=self.timeout,
            )

            if response.status_code == 200:
                logger.info(f"Sync request {request_id} approved")
                return True
            elif response.status_code == 401:
                logger.error("Unauthorized: Invalid or expired session")
                return False
            elif response.status_code == 403:
                logger.error("Forbidden: Insufficient privileges")
                return False
            else:
                logger.error(
                    f"Approval failed: {response.status_code} {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Catalog service request failed: {e}")
            return False

    def health_check(self) -> bool:
        """
        Check if catalog service is healthy.

        Returns:
            True if service is reachable and healthy
        """
        try:
            response = self._session.get(
                f"{self.service_url}/health",
                timeout=5,
            )
            return response.status_code == 200

        except requests.exceptions.RequestException:
            return False


class LocalCatalogClient:
    """
    Local catalog implementation for development/testing.

    Provides the same interface as CatalogClient but uses the local
    repository database directly. Does not require a remote service.
    """

    def __init__(
        self,
        repository_path: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        from ..repository.sqlite import SQLiteBackend

        if repository_path is None:
            repository_path = str(Path.home() / ".sim2l" / "simulations.db")

        self.repository = SQLiteBackend(repository_path)
        self.session_id = session_id

    def search(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = "active",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search local repository."""
        # SQLiteBackend exposes `list`, not `list_all`.
        simulations = self.repository.list(tags=tags, status=status)

        # Filter by query
        if query:
            simulations = [
                s for s in simulations if query.lower() in s["name"].lower()
            ]

        return simulations[:limit]

    def get_simulation(
        self, name: str, version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get simulation from local repository."""
        try:
            sim_def = self.repository.get(name, version)
            if sim_def:
                return sim_def.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to get simulation: {e}")
            return None

    def register_simulation(self, **kwargs) -> bool:
        """Local registration is a no-op (use repository.deploy instead)."""
        logger.info("Local catalog: Use repository.deploy() to register simulations")
        return True

    def update_simulation(self, simulation_id: int, updates: Dict[str, Any]) -> bool:
        """Local update not implemented."""
        logger.warning("Local catalog does not support updates")
        return False

    def record_execution(self, **kwargs) -> bool:
        """Local execution recording is handled by repository."""
        return True

    def get_stats(self, simulation_id: int) -> Optional[Dict[str, Any]]:
        """Get stats from local repository."""
        # This would require aggregating execution data
        # For now, return basic info
        return {"simulation_id": simulation_id, "local": True}

    def sync_local_simulations(
        self, repository_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sync is a no-op for local catalog."""
        return {
            "scanned": 0,
            "already_registered": 0,
            "sync_requested": 0,
            "errors": 0,
        }

    def health_check(self) -> bool:
        """Local catalog is always healthy."""
        return True
