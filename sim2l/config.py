"""Global configuration management"""

import os
from pathlib import Path
from typing import Optional
import json
import logging

class Config:
    """Global sim2l configuration"""

    def __init__(self):
        self.db_path = self._default_db_path()
        self.cache_enabled = True
        self.default_executor = "local"
        self.artifact_storage = "database"  # or "filesystem"
        self.artifact_base_path = None
        self.log_level = "INFO"
        self.debug_mode = False  # Enable DEBUG logging across all services
        self._logger = None

        # Database service configuration
        self.use_run_database = False  # Enable per-run databases
        self.run_db_base_path = None  # Base path for run databases (default: ~/.sim2l/runs)

        # Cache service configuration
        self.cache_service_url = None  # Remote cache service URL (None = local cache)
        self.cache_session_id = None  # Session ID for cache service

        # Catalog service configuration
        self.catalog_service_url = None  # Master catalog URL (None = local catalog)
        self.catalog_session_id = None  # Session ID for catalog service
        self.catalog_auto_sync = True  # Auto-sync new simulations to catalog

        # Results service configuration
        self.results_service_url = None  # Results service URL (None = local results DB)
        self.results_session_id = None  # Session ID for results service

    def _default_db_path(self) -> Path:
        """Default database location"""
        # Check environment variable first
        env_path = os.environ.get("SIM2L_DB_PATH")
        if env_path:
            return Path(env_path)

        home = Path.home()
        sim2l_dir = home / ".sim2l"
        sim2l_dir.mkdir(exist_ok=True)
        return sim2l_dir / "simulations.db"

    def load_from_file(self, config_path: Path):
        """Load configuration from JSON file"""
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(self, key):
                        # Convert string paths to Path objects
                        if key.endswith('_path') and value:
                            value = Path(value)
                        setattr(self, key, value)

    def save_to_file(self, config_path: Path):
        """Save configuration to JSON file"""
        data = {
            "db_path": str(self.db_path),
            "cache_enabled": self.cache_enabled,
            "default_executor": self.default_executor,
            "artifact_storage": self.artifact_storage,
            "artifact_base_path": str(self.artifact_base_path) if self.artifact_base_path else None,
            "log_level": self.log_level,
            "debug_mode": self.debug_mode,
            "use_run_database": self.use_run_database,
            "run_db_base_path": str(self.run_db_base_path) if self.run_db_base_path else None,
            "cache_service_url": self.cache_service_url,
            "catalog_service_url": self.catalog_service_url,
            "catalog_auto_sync": self.catalog_auto_sync,
            "results_service_url": self.results_service_url,
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_logger(self) -> logging.Logger:
        """Get configured logger"""
        if self._logger is None:
            self._logger = logging.getLogger("sim2l")
            # Use DEBUG if debug_mode is enabled, otherwise use configured log_level
            level = logging.DEBUG if self.debug_mode else getattr(logging, self.log_level)
            self._logger.setLevel(level)

            # Add console handler if not already added
            if not self._logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)

        return self._logger


# Global config instance
_config = Config()

# Load environment variables
if os.environ.get("SIM2L_CACHE_ENABLED"):
    _config.cache_enabled = os.environ["SIM2L_CACHE_ENABLED"].lower() in ("true", "1", "yes")
if os.environ.get("SIM2L_DEFAULT_EXECUTOR"):
    _config.default_executor = os.environ["SIM2L_DEFAULT_EXECUTOR"]
if os.environ.get("SIM2L_LOG_LEVEL"):
    _config.log_level = os.environ["SIM2L_LOG_LEVEL"]
if os.environ.get("SIM2L_DEBUG_MODE"):
    _config.debug_mode = os.environ["SIM2L_DEBUG_MODE"].lower() in ("true", "1", "yes")
if os.environ.get("SIM2L_USE_RUN_DATABASE"):
    _config.use_run_database = os.environ["SIM2L_USE_RUN_DATABASE"].lower() in ("true", "1", "yes")
if os.environ.get("SIM2L_RUN_DB_BASE_PATH"):
    _config.run_db_base_path = Path(os.environ["SIM2L_RUN_DB_BASE_PATH"])
if os.environ.get("SIM2L_CACHE_SERVICE_URL"):
    _config.cache_service_url = os.environ["SIM2L_CACHE_SERVICE_URL"]
if os.environ.get("SIM2L_CACHE_SESSION_ID"):
    _config.cache_session_id = os.environ["SIM2L_CACHE_SESSION_ID"]
if os.environ.get("SIM2L_CATALOG_SERVICE_URL"):
    _config.catalog_service_url = os.environ["SIM2L_CATALOG_SERVICE_URL"]
if os.environ.get("SIM2L_CATALOG_SESSION_ID"):
    _config.catalog_session_id = os.environ["SIM2L_CATALOG_SESSION_ID"]
if os.environ.get("SIM2L_CATALOG_AUTO_SYNC"):
    _config.catalog_auto_sync = os.environ["SIM2L_CATALOG_AUTO_SYNC"].lower() in ("true", "1", "yes")
if os.environ.get("SIM2L_RESULTS_SERVICE_URL"):
    _config.results_service_url = os.environ["SIM2L_RESULTS_SERVICE_URL"]
if os.environ.get("SIM2L_RESULTS_SESSION_ID"):
    _config.results_session_id = os.environ["SIM2L_RESULTS_SESSION_ID"]

# Try to load from user config file
_user_config = Path.home() / ".sim2l" / "config.json"
if _user_config.exists():
    _config.load_from_file(_user_config)


def get_config() -> Config:
    """Get global configuration"""
    return _config


def configure(**kwargs):
    """Update global configuration

    Args:
        db_path: Path to simulation database
        cache_enabled: Enable/disable caching
        default_executor: Default executor type
        artifact_storage: "database" or "filesystem"
        artifact_base_path: Base path for filesystem artifact storage
        log_level: Logging level
    """
    for key, value in kwargs.items():
        if hasattr(_config, key):
            if key.endswith('_path') and value and not isinstance(value, Path):
                value = Path(value)
            setattr(_config, key, value)
        else:
            raise ValueError(f"Unknown configuration option: {key}")


def get_logger() -> logging.Logger:
    """Get sim2l logger"""
    return _config.get_logger()
