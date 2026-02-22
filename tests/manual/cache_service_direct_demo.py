#!/usr/bin/env python3
# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""
Manual demo: verify cache service set/get behavior directly.

Run:
    python3 tests/manual/cache_service_direct_demo.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sim2l.database import CacheClient  # noqa: E402


def main() -> int:
    print("Starting cache service...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sim2l.services.cache_service",
            "--backend",
            "postgresql",
            "--db-url",
            "postgresql://sim2l:sim2l_password@localhost:5432/sim2l_cache",
            "--no-auth",
            "--port",
            "8001",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(3)

    try:
        print("\nCreating cache client...")
        client = CacheClient(service_url="http://localhost:8001")

        print("\nTesting cache.set()...")
        test_inputs = {
            "temperature": 300,
            "power": 10,
            "grid_size": 30,
            "iterations": 200,
        }
        input_hash = hashlib.sha256(
            json.dumps(test_inputs, sort_keys=True).encode()
        ).hexdigest()
        print(f"  Input hash: {input_hash[:16]}...")

        success = client.set(
            cache_key="test-cache-key-123",
            simulation_id=1,
            simulation_name="thermal_analysis",
            simulation_version="1.0.0",
            execution_id="test-exec-123",
            squid_id="test-squid-123",
            input_hash=input_hash,
            run_db_path="",
            ttl_seconds=None,
            metadata={"test": "data"},
        )
        print(f"  Set result: {success}")

        if not success:
            print("\nERROR: Failed to store cache entry")
            return 1

        print("\nTesting cache.get()...")
        cached = client.get("test-cache-key-123")
        print(f"  Get result: {cached}")
        return 0
    finally:
        print("\nStopping cache service...")
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
