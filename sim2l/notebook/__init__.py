# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Jupyter notebook integration module"""

from .magics import load_ipython_extension, Sim2lMagics

__all__ = [
    "load_ipython_extension",
    "Sim2lMagics",
]
