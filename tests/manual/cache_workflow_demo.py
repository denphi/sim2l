#!/usr/bin/env python3
# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Manual demo: verify cache hits for repeated workflow parameters.

Run:
    python3 tests/manual/cache_workflow_demo.py
"""

from __future__ import annotations

import sim2l
from sim2l.executor import NotebookExecutor


def _read_output(outputs, key: str):
    """Read an output field from OutputData or dict-like containers."""
    if outputs is None:
        return None
    if hasattr(outputs, key):
        return getattr(outputs, key)
    if hasattr(outputs, "dict"):
        return outputs.dict().get(key)
    if isinstance(outputs, dict):
        return outputs.get(key)
    return None


def main() -> int:
    sim2l.configure(
        cache_service_url="http://localhost:8001",
        results_service_url="http://localhost:8003",
        debug_mode=True,
    )

    sim = sim2l.load_simulation("thermal_analysis")
    executor = NotebookExecutor(cache=True, register_results=True)

    test_cases = [
        ("Test 1 (should be NEW)", {"temperature": 300, "power": 10, "grid_size": 30, "iterations": 200}),
        ("Test 2 (should be NEW)", {"temperature": 350, "power": 20, "grid_size": 30, "iterations": 200}),
        ("Test 3 (should be CACHE HIT)", {"temperature": 300, "power": 10, "grid_size": 30, "iterations": 200}),
        ("Test 4 (should be CACHE HIT)", {"temperature": 350, "power": 20, "grid_size": 30, "iterations": 200}),
    ]

    for label, params in test_cases:
        print(f"\n=== {label} ===")
        result = executor.execute(sim, params)
        max_temp = _read_output(result.outputs, "max_temperature")
        print(f"Result: Max T = {max_temp}")

    print("\n=== Summary ===")
    print("Cache should have 2 hits (tests 3 and 4)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
