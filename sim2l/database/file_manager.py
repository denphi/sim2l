# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
File Manager for sim2l using the new cache system.

This module provides file and folder management capabilities similar to the
legacy papers/ implementation but built on the new cache service architecture.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

from .cache_client import CacheClient, LocalCacheClient
from .session_manager import get_session_manager


class FileManager:
    """
    Manages files and folders using the cache service.

    Supports metadata storage, folder hierarchy management, and file operations
    backed by local cache or the remote cache service.
    """

    def __init__(
        self,
        cache_url: Optional[str] = None,
        session_id: Optional[str] = None,
        simulation_name: str = "file_manager",
        simulation_version: str = "1.0.0"
    ):
        """
        Initialize the FileManager.

        Args:
            cache_url: URL of cache service (None = local mode)
            session_id: Session ID for authentication
            simulation_name: Name to use for cache entries
            simulation_version: Version to use for cache entries
        """
        if cache_url:
            self.cache = CacheClient(cache_url, session_id=session_id)
        else:
            self.cache = LocalCacheClient()

        self.simulation_name = simulation_name
        self.simulation_version = simulation_version
        self._simulation_id = 0  # Files use simulation_id=0

    def _generate_id(self) -> str:
        """Generate a unique ID for a file or folder."""
        return datetime.now().strftime('%Y%m-%d%H-%M%S-') + str(uuid4())

    def _make_cache_key(self, file_id: str) -> str:
        """Generate cache key for a file ID."""
        return f"file:{file_id}"

    def _get_timestamp(self) -> float:
        """Get current timestamp."""
        return datetime.timestamp(datetime.now())

    def create_file(
        self,
        name: str,
        size: int,
        uri: str,
        creator: str,
        parent_id: Optional[str] = None,
        site_name: Optional[str] = None,
        url: Optional[str] = None,
        file_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new file entry.

        Args:
            name: File name
            size: File size in bytes
            uri: File URI/path
            creator: User who created the file
            parent_id: Parent folder ID (None = root)
            site_name: Optional site name
            url: Optional URL
            file_id: Optional custom ID (auto-generated if None)
            metadata: Optional additional metadata

        Returns:
            Dict containing file information
        """
        file_id = file_id or self._generate_id()
        parent_id = parent_id or '0'
        timestamp = self._get_timestamp()

        file_data = {
            'id': file_id,
            'name': name,
            'size': size,
            'uri': uri,
            'creator': creator,
            'parent_id': parent_id,
            'site_name': site_name,
            'url': url,
            'is_folder': False,
            'status': True,
            'date_created': timestamp,
            'date_modified': timestamp,
        }

        # Add custom metadata if provided
        if metadata:
            file_data['metadata'] = metadata

        # Store in cache
        self.cache.set(
            cache_key=self._make_cache_key(file_id),
            simulation_id=self._simulation_id,
            simulation_name=self.simulation_name,
            simulation_version=self.simulation_version,
            execution_id=file_id,
            squid_id=f"{self.simulation_name}/{self.simulation_version}/{file_id}",
            input_hash=file_id,
            run_db_path="",
            metadata=file_data
        )

        # If has parent, add to parent's objects list
        if parent_id != '0':
            self._add_to_folder(parent_id, file_id)

        return file_data

    def create_folder(
        self,
        name: str,
        creator: str,
        parent_id: Optional[str] = None,
        folder_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new folder.

        Args:
            name: Folder name
            creator: User who created the folder
            parent_id: Parent folder ID (None = root)
            folder_id: Optional custom ID (auto-generated if None)
            metadata: Optional additional metadata

        Returns:
            Dict containing folder information
        """
        folder_id = folder_id or self._generate_id()
        parent_id = parent_id or '0'
        timestamp = self._get_timestamp()

        folder_data = {
            'id': folder_id,
            'name': name,
            'creator': creator,
            'parent_id': parent_id,
            'is_folder': True,
            'status': True,
            'objects': [],  # List of child file/folder IDs
            'date_created': timestamp,
            'date_modified': timestamp,
        }

        # Add custom metadata if provided
        if metadata:
            folder_data['metadata'] = metadata

        # Store in cache
        self.cache.set(
            cache_key=self._make_cache_key(folder_id),
            simulation_id=self._simulation_id,
            simulation_name=self.simulation_name,
            simulation_version=self.simulation_version,
            execution_id=folder_id,
            squid_id=f"{self.simulation_name}/{self.simulation_version}/{folder_id}",
            input_hash=folder_id,
            run_db_path="",
            metadata=folder_data
        )

        # If has parent, add to parent's objects list
        if parent_id != '0':
            self._add_to_folder(parent_id, folder_id)

        return folder_data

    def get_file(self, file_id: str, expand_children: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get file or folder by ID.

        Args:
            file_id: File or folder ID
            expand_children: If True and this is a folder, expand child objects

        Returns:
            File/folder data or None if not found
        """
        result = self.cache.get(self._make_cache_key(file_id))

        if result is None:
            return None

        file_data = result.get('metadata', {})

        # If folder and expand requested, get child objects
        if expand_children and file_data.get('is_folder', False):
            child_ids = file_data.get('objects', [])
            if child_ids:
                file_data['objects'] = [
                    self.get_file(child_id)
                    for child_id in child_ids
                ]
                # Filter out None values (deleted children)
                file_data['objects'] = [obj for obj in file_data['objects'] if obj]

        return file_data

    def update_file(self, file_id: str, **updates) -> bool:
        """
        Update file metadata.

        Args:
            file_id: File ID
            **updates: Fields to update

        Returns:
            True if successful, False if file not found
        """
        file_data = self.get_file(file_id)
        if not file_data:
            return False

        # Update fields
        file_data.update(updates)
        file_data['date_modified'] = self._get_timestamp()

        # Save back to cache
        self.cache.set(
            cache_key=self._make_cache_key(file_id),
            simulation_id=self._simulation_id,
            simulation_name=self.simulation_name,
            simulation_version=self.simulation_version,
            execution_id=file_id,
            squid_id=f"{self.simulation_name}/{self.simulation_version}/{file_id}",
            input_hash=file_id,
            run_db_path="",
            metadata=file_data
        )

        return True

    def delete_file(self, file_id: str, recursive: bool = False) -> bool:
        """
        Delete file or folder.

        Args:
            file_id: File or folder ID
            recursive: If True, delete folder contents recursively

        Returns:
            True if successful, False if not found
        """
        file_data = self.get_file(file_id)
        if not file_data:
            return False

        # If folder, optionally delete children
        if file_data.get('is_folder', False) and recursive:
            child_ids = file_data.get('objects', [])
            for child_id in child_ids:
                self.delete_file(child_id, recursive=True)

        # Remove from parent folder
        parent_id = file_data.get('parent_id')
        if parent_id and parent_id != '0':
            self._remove_from_folder(parent_id, file_id)

        # Delete from cache by invalidating
        self.cache.invalidate(pattern=f"file:{file_id}")

        return True

    def move_file(self, file_id: str, new_parent_id: str) -> bool:
        """
        Move file or folder to a different parent.

        Args:
            file_id: File or folder ID to move
            new_parent_id: New parent folder ID ('0' for root)

        Returns:
            True if successful, False if file not found
        """
        file_data = self.get_file(file_id)
        if not file_data:
            return False

        old_parent_id = file_data.get('parent_id')

        # Remove from old parent
        if old_parent_id and old_parent_id != '0':
            self._remove_from_folder(old_parent_id, file_id)

        # Add to new parent
        if new_parent_id != '0':
            self._add_to_folder(new_parent_id, file_id)

        # Update file's parent_id
        file_data['parent_id'] = new_parent_id
        file_data['date_modified'] = self._get_timestamp()

        # Save updated file
        self.cache.set(
            cache_key=self._make_cache_key(file_id),
            simulation_id=self._simulation_id,
            simulation_name=self.simulation_name,
            simulation_version=self.simulation_version,
            execution_id=file_id,
            squid_id=f"{self.simulation_name}/{self.simulation_version}/{file_id}",
            input_hash=file_id,
            run_db_path="",
            metadata=file_data
        )

        return True

    def list_folder(self, folder_id: str = '0') -> List[Dict[str, Any]]:
        """
        List contents of a folder.

        Args:
            folder_id: Folder ID ('0' for root)

        Returns:
            List of file/folder dictionaries
        """
        if folder_id == '0':
            # Root folder - need to find all files with parent_id='0'
            # This is a limitation of cache-based storage
            # In practice, you'd maintain a root folder object
            return []

        folder = self.get_file(folder_id, expand_children=True)
        if not folder or not folder.get('is_folder', False):
            return []

        return folder.get('objects', [])

    def get_run_files(self, execution_id: str) -> List[Dict[str, Any]]:
        """
        Get all files generated by a specific sim2l execution.

        This queries the run database to get all artifacts (files) from a run.

        Args:
            execution_id: Execution ID of the sim2l run

        Returns:
            List of file dictionaries with metadata
        """
        from .run_database import RunDatabase

        try:
            run_db = RunDatabase(execution_id)
            artifacts = run_db.get_artifacts()

            # Convert artifacts to file metadata format
            files = []
            for artifact in artifacts:
                file_info = {
                    'id': f"{execution_id}:{artifact['name']}",
                    'name': artifact['name'],
                    'execution_id': execution_id,
                    'category': artifact['category'],
                    'content_type': artifact['content_type'],
                    'size': len(artifact.get('content', b'')),
                    'uri': artifact.get('path', ''),
                    'date_created': artifact['created_at'],
                    'is_folder': False,
                    'metadata': artifact.get('metadata', {})
                }
                files.append(file_info)

            return files
        except Exception as e:
            # Run database not found or error reading
            return []

    def get_simulation_files(
        self,
        simulation_name: str,
        simulation_version: Optional[str] = None,
        execution_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all files for a simulation (optionally filtered by version/execution).

        This uses the catalog service to find executions and then retrieves
        files from each execution's run database.

        Args:
            simulation_name: Name of the simulation
            simulation_version: Optional version filter
            execution_id: Optional specific execution ID

        Returns:
            List of file dictionaries
        """
        from .catalog_client import CatalogClient
        from .run_database import RunDatabase

        if execution_id:
            # Specific execution requested
            return self.get_run_files(execution_id)

        # Query catalog for executions
        try:
            catalog = CatalogClient(
                catalog_url=getattr(self.cache, 'base_url', None),
                session_id=getattr(self.cache, 'session_id', None)
            )

            # Get simulation info
            sim_info = catalog.get_simulation(simulation_name, simulation_version)
            if not sim_info:
                return []

            # Get execution stats to find all executions
            stats = catalog.get_simulation_stats(sim_info['id'])
            execution_ids = [stat['execution_id'] for stat in stats.get('recent_executions', [])]

            # Get files from all executions
            all_files = []
            for exec_id in execution_ids:
                files = self.get_run_files(exec_id)
                all_files.extend(files)

            return all_files
        except Exception as e:
            return []

    def export_run_file(
        self,
        execution_id: str,
        file_name: str,
        output_path: str
    ) -> bool:
        """
        Export a file from a run database to the filesystem.

        Args:
            execution_id: Execution ID of the run
            file_name: Name of the file in the run database
            output_path: Path where to save the file

        Returns:
            True if successful, False otherwise
        """
        from .run_database import RunDatabase

        try:
            run_db = RunDatabase(execution_id)
            artifacts = run_db.get_artifacts()

            # Find the requested file
            for artifact in artifacts:
                if artifact['name'] == file_name:
                    # Write content to output path
                    content = artifact.get('content', b'')

                    # Create directory if needed
                    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

                    # Write file
                    mode = 'wb' if isinstance(content, bytes) else 'w'
                    with open(output_path, mode) as f:
                        f.write(content)

                    return True

            return False
        except Exception as e:
            return False

    def search(
        self,
        name_pattern: Optional[str] = None,
        creator: Optional[str] = None,
        is_folder: Optional[bool] = None,
        parent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for files/folders matching criteria.

        Not implemented: the cache service does not support arbitrary queries.
        To search files, either maintain a separate index, use the catalog
        service, or track file IDs in your own data structure.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "search() is not implemented for cache-backed FileManager. "
            "Use the catalog service or maintain a separate file index."
        )

    def _add_to_folder(self, folder_id: str, object_id: str) -> bool:
        """Add an object to a folder's objects list."""
        folder = self.get_file(folder_id)
        if not folder or not folder.get('is_folder', False):
            return False

        objects = folder.get('objects', [])
        if object_id not in objects:
            objects.append(object_id)
            folder['objects'] = objects
            folder['date_modified'] = self._get_timestamp()

            # Save updated folder
            self.cache.set(
                cache_key=self._make_cache_key(folder_id),
                simulation_id=self._simulation_id,
                simulation_name=self.simulation_name,
                simulation_version=self.simulation_version,
                execution_id=folder_id,
                squid_id=f"{self.simulation_name}/{self.simulation_version}/{folder_id}",
                input_hash=folder_id,
                run_db_path="",
                metadata=folder
            )

        return True

    def _remove_from_folder(self, folder_id: str, object_id: str) -> bool:
        """Remove an object from a folder's objects list."""
        folder = self.get_file(folder_id)
        if not folder or not folder.get('is_folder', False):
            return False

        objects = folder.get('objects', [])
        if object_id in objects:
            objects.remove(object_id)
            folder['objects'] = objects
            folder['date_modified'] = self._get_timestamp()

            # Save updated folder
            self.cache.set(
                cache_key=self._make_cache_key(folder_id),
                simulation_id=self._simulation_id,
                simulation_name=self.simulation_name,
                simulation_version=self.simulation_version,
                execution_id=folder_id,
                squid_id=f"{self.simulation_name}/{self.simulation_version}/{folder_id}",
                input_hash=folder_id,
                run_db_path="",
                metadata=folder
            )

        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get file manager statistics from cache."""
        return self.cache.get_stats(simulation_id=self._simulation_id)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # Close cache connection if needed
        if hasattr(self.cache, '__exit__'):
            self.cache.__exit__(exc_type, exc_val, exc_tb)
        return False
