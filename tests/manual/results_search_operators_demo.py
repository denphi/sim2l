#!/usr/bin/env python3
"""
Manual demo: exercise results search operators against the Results service.

Run:
    python3 tests/manual/results_search_operators_demo.py
"""

from __future__ import annotations

import requests


def _run_case(title: str, input_filters: dict):
    print("=" * 70)
    print(title)
    print("=" * 70)

    response = requests.post(
        "http://localhost:8003/search",
        headers={"Content-Type": "application/json", "X-Session-ID": "test"},
        json={"input_filters": input_filters, "limit": 10},
        timeout=10,
    )
    result = response.json()
    print(f"Status: {response.status_code}")
    print(f"Results: {result.get('count', 0)}")

    for row in result.get("results", [])[:5]:
        params = row.get("input_params", {})
        print(f"  - grid_size={params.get('grid_size')}, temperature={params.get('temperature')}")
    print()


def main() -> int:
    scenarios = [
        ("TEST 1: Equality (grid_size = 30)", {"grid_size": 30}),
        ("TEST 2: Greater than or equal (grid_size >= 10)", {"grid_size": {"$gte": 10}}),
        ("TEST 3: Less than (grid_size < 35)", {"grid_size": {"$lt": 35}}),
        (
            "TEST 4: Range (grid_size >= 25 AND grid_size <= 35)",
            {"grid_size": {"$gte": 25, "$lte": 35}},
        ),
        (
            "TEST 5: Multiple filters (grid_size >= 30 AND temperature >= 300)",
            {"grid_size": {"$gte": 30}, "temperature": {"$gte": 300}},
        ),
    ]

    for title, filters in scenarios:
        _run_case(title, filters)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
