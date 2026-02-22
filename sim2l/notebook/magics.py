# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""IPython magic commands for sim2l

This module provides cell magics for defining simulations in Jupyter notebooks:
- %%sim2l_inputs - Define input schema
- %%sim2l_outputs - Define output schema

Usage in notebook:
    %load_ext sim2l.notebook

    %%sim2l_inputs
    temperature:
      type: Number
      units: kelvin
"""

from IPython.core.magic import Magics, magics_class, cell_magic
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
import yaml

# Global storage for schemas in notebook context
_notebook_schemas = {
    'inputs': None,
    'outputs': None
}


@magics_class
class Sim2lMagics(Magics):
    """IPython magic commands for sim2l"""

    @cell_magic
    def sim2l_inputs(self, line, cell):
        """Define input schema for simulation

        Usage:
            %%sim2l_inputs
            temperature:
              type: Number
              units: kelvin
              min: 0
              max: 1000
        """
        from ..schema import InputSchema

        # Parse YAML
        try:
            schema_dict = yaml.safe_load(cell)
            if schema_dict is None:
                schema_dict = {}

            # Create InputSchema
            schema = InputSchema.from_dict(schema_dict)

            # Store in global context
            _notebook_schemas['inputs'] = schema

            # Store in IPython user namespace
            self.shell.user_ns['_sim2l_inputs'] = schema

            print(f"✓ Defined {len(schema.fields)} input parameters")

        except Exception as e:
            print(f"✗ Error parsing input schema: {e}")
            raise

    @cell_magic
    def sim2l_outputs(self, line, cell):
        """Define output schema for simulation

        Usage:
            %%sim2l_outputs
            max_temperature:
              type: Number
              units: kelvin
        """
        from ..schema import OutputSchema

        # Parse YAML
        try:
            schema_dict = yaml.safe_load(cell)
            if schema_dict is None:
                schema_dict = {}

            # Create OutputSchema
            schema = OutputSchema.from_dict(schema_dict)

            # Store in global context
            _notebook_schemas['outputs'] = schema

            # Store in IPython user namespace
            self.shell.user_ns['_sim2l_outputs'] = schema

            print(f"✓ Defined {len(schema.fields)} output parameters")

        except Exception as e:
            print(f"✗ Error parsing output schema: {e}")
            raise


def load_ipython_extension(ipython):
    """Load the extension in IPython

    This is called when running:
        %load_ext sim2l.notebook
    """
    ipython.register_magics(Sim2lMagics)
    print("sim2l magics loaded. Use %%sim2l_inputs and %%sim2l_outputs")


def unload_ipython_extension(ipython):
    """Unload the extension"""
    pass


def get_notebook_schemas():
    """Get schemas defined in current notebook

    Returns:
        Tuple of (inputs, outputs)
    """
    return _notebook_schemas['inputs'], _notebook_schemas['outputs']


def get_notebook_inputs():
    """Get input schema from current notebook

    Returns:
        InputSchema or None
    """
    return _notebook_schemas['inputs']


def get_notebook_outputs():
    """Get output schema from current notebook

    Returns:
        OutputSchema or None
    """
    return _notebook_schemas['outputs']
