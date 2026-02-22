# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Notebook parsing utilities"""

import json
from pathlib import Path
from typing import Tuple
import re

from ..schema import InputSchema, OutputSchema


def parse_notebook(notebook_path: Path) -> Tuple[InputSchema, OutputSchema, bytes]:
    """Parse Jupyter notebook to extract schemas and workflow

    Args:
        notebook_path: Path to notebook file

    Returns:
        Tuple of (input_schema, output_schema, notebook_bytes)
    """
    with open(notebook_path, 'r') as f:
        notebook = json.load(f)

    # Extract schemas from cells
    inputs_yaml = None
    outputs_yaml = None

    for cell in notebook.get('cells', []):
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source'])

            # Check for sim2l magic commands
            if source.strip().startswith('%%sim2l_inputs'):
                # Extract YAML content after magic command
                yaml_content = '\n'.join(source.split('\n')[1:])
                inputs_yaml = yaml_content

            elif source.strip().startswith('%%sim2l_outputs'):
                # Extract YAML content after magic command
                yaml_content = '\n'.join(source.split('\n')[1:])
                outputs_yaml = yaml_content

            # Also check for legacy %%yaml INPUTS/OUTPUTS format
            elif source.strip().startswith('%%yaml INPUTS'):
                yaml_content = '\n'.join(source.split('\n')[1:])
                inputs_yaml = yaml_content

            elif source.strip().startswith('%%yaml OUTPUTS'):
                yaml_content = '\n'.join(source.split('\n')[1:])
                outputs_yaml = yaml_content

    # Parse schemas
    if inputs_yaml is None:
        raise ValueError(f"No inputs schema found in notebook {notebook_path}")

    if outputs_yaml is None:
        raise ValueError(f"No outputs schema found in notebook {notebook_path}")

    inputs = InputSchema.from_yaml(inputs_yaml)
    outputs = OutputSchema.from_yaml(outputs_yaml)

    # Read notebook bytes
    with open(notebook_path, 'rb') as f:
        notebook_bytes = f.read()

    return inputs, outputs, notebook_bytes


def extract_yaml_from_cell(source: str) -> str:
    """Extract YAML content from a notebook cell

    Args:
        source: Cell source code

    Returns:
        YAML content
    """
    lines = source.split('\n')

    # Skip magic command line
    if lines[0].startswith('%%'):
        lines = lines[1:]

    return '\n'.join(lines)
