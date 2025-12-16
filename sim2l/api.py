"""High-level API functions for sim2l"""

from pathlib import Path
from typing import Union, Optional, Dict, Any
import os

from .definition import SimulationDefinition
from .repository import SimulationRepository
from .schema import InputSchema
from .config import get_logger

logger = get_logger()

# Global context for notebook execution
_notebook_context = {}


def deploy_simulation(
    notebook: Union[str, Path],
    name: str,
    version: str,
    description: str = "",
    author: str = "",
    tags: Optional[list] = None,
    dependencies: Optional[list] = None,
) -> int:
    """Deploy a simulation from a Jupyter notebook

    Args:
        notebook: Path to notebook file
        name: Simulation name
        version: Semantic version
        description: Description
        author: Author name
        tags: List of tags
        dependencies: List of package dependencies

    Returns:
        Simulation ID in database

    Example:
        >>> deploy_simulation(
        ...     notebook="thermal_sim.ipynb",
        ...     name="thermal_analysis",
        ...     version="1.0.0",
        ...     description="2D thermal diffusion",
        ...     tags=["physics", "thermal"]
        ... )
    """
    # Create simulation definition from notebook
    sim_def = SimulationDefinition.from_notebook(
        notebook_path=notebook,
        name=name,
        version=version,
        description=description,
        author=author,
        tags=tags,
        dependencies=dependencies,
    )

    # Deploy to repository
    repo = SimulationRepository()
    sim_id = repo.deploy(sim_def)

    logger.info(f"Deployed simulation {name} v{version} (ID: {sim_id})")

    return sim_id


def get_inputs() -> InputSchema:
    """Get input schema in notebook authoring context

    This function is used inside notebooks to get the input schema
    for interactive testing during authoring.

    Returns:
        InputSchema with default values

    Example (in notebook):
        >>> # First, load the extension and define inputs
        >>> %load_ext sim2l.notebook
        >>> %%sim2l_inputs
        >>> temperature:
        >>>   type: Number
        >>>   units: kelvin
        >>>
        >>> # Then get inputs for testing
        >>> inputs = get_inputs()
        >>> inputs.temperature = 350
    """
    # Try to get from IPython namespace (set by magic)
    try:
        from IPython import get_ipython
        ipython = get_ipython()
        if ipython is not None and '_sim2l_inputs' in ipython.user_ns:
            return ipython.user_ns['_sim2l_inputs']
    except Exception:
        pass

    # Try from global context
    if 'inputs' in _notebook_context:
        return _notebook_context['inputs']

    # Try to get from notebook magic module
    try:
        from .notebook.magics import get_notebook_inputs
        inputs = get_notebook_inputs()
        if inputs is not None:
            return inputs
    except Exception:
        pass

    raise RuntimeError(
        "get_inputs() must be called after defining inputs with %%sim2l_inputs\n"
        "Load the extension first: %load_ext sim2l.notebook"
    )


def save_outputs(**outputs: Any):
    """Save simulation outputs in notebook

    Saves outputs to both:
    1. SQLite database (if execution_id is set in environment)
    2. Scrapbook (for backward compatibility)

    Args:
        **outputs: Output variables as keyword arguments

    Example (in notebook):
        >>> save_outputs(
        ...     max_temperature=450.5,
        ...     temperature_distribution=temp_array,
        ...     plot="thermal_plot.png"
        ... )
    """
    # Store in global context
    _notebook_context['outputs'] = outputs

    # Save to database if we're in an execution context
    execution_id = os.environ.get('SIM2L_EXECUTION_ID')
    if execution_id:
        try:
            import sqlite3
            from .utils.serialization import serialize_value

            # Get database path from config or environment
            db_path = os.environ.get('SIM2L_DB_PATH')
            if not db_path:
                from .config import get_config
                db_path = get_config().db_path

            # Save each output to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            for name, value in outputs.items():
                # Serialize value
                serialized = serialize_value(value)

                # Insert or replace output
                cursor.execute("""
                    INSERT OR REPLACE INTO outputs (
                        execution_id, name, type, value
                    ) VALUES (?, ?, ?, ?)
                """, (
                    execution_id,
                    name,
                    type(value).__name__,
                    serialized,
                ))

            conn.commit()
            conn.close()
            logger.info(f"Saved {len(outputs)} outputs to database for execution {execution_id}")

        except Exception as e:
            logger.error(f"Failed to save outputs to database: {e}")
            raise  # Re-raise to make it clear something went wrong

    # Also try scrapbook for backward compatibility (optional)
    try:
        import scrapbook as sb
        for name, value in outputs.items():
            try:
                sb.glue(name, value)
            except (NotImplementedError, Exception) as e:
                # Skip values that scrapbook can't handle (numpy arrays, etc.)
                logger.debug(f"Scrapbook cannot encode '{name}': {e}")
    except ImportError:
        logger.debug("scrapbook not installed")


def set_notebook_context(inputs: InputSchema = None, outputs: Dict[str, Any] = None):
    """Set notebook execution context (internal use)

    Args:
        inputs: Input schema instance
        outputs: Output values dictionary
    """
    if inputs is not None:
        _notebook_context['inputs'] = inputs
    if outputs is not None:
        _notebook_context['outputs'] = outputs


def get_notebook_context() -> dict:
    """Get notebook execution context (internal use)

    Returns:
        Dictionary with 'inputs' and 'outputs' keys
    """
    return _notebook_context
