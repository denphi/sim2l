# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Unit registry wrapper using Pint"""

from pint import UnitRegistry

# Global unit registry instance
_ureg = None


def get_unit_registry() -> UnitRegistry:
    """Get the global unit registry

    Returns:
        UnitRegistry instance
    """
    global _ureg
    if _ureg is None:
        _ureg = UnitRegistry()

        # Define common aliases (matching simtool)
        _ureg.define("angstrom = 1e-10 * meter = Å")

    return _ureg
