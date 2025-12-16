"""Result management module"""

from .result import ExecutionResult, load_result
from .outputs import OutputData

__all__ = [
    "ExecutionResult",
    "OutputData",
    "load_result",
]
