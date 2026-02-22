# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Result management module"""

from .result import ExecutionResult, load_result
from .outputs import OutputData

__all__ = [
    "ExecutionResult",
    "OutputData",
    "load_result",
]
