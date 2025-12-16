"""Jupyter notebook integration module"""

from .magics import load_ipython_extension, Sim2lMagics

__all__ = [
    "load_ipython_extension",
    "Sim2lMagics",
]
