# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Smoke tests for simtool package wiring.

These checks explain and verify the most basic expectation:
the package can be imported in the current test environment.
"""

import simtool


def test_simtool_module_is_importable():
    """Validate that `simtool` can be imported before running deeper tests."""
    assert simtool is not None
