#!/usr/bin/env python3
"""
Test script to verify all sim2l services are working.
"""

import requests
import sys


def test_service(name, url):
    """Test if a service is responding."""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ {name}: {data.get('status', 'unknown')}")
            print(f"  Backend: {data.get('backend', 'unknown')}")
            if 'simulations' in data:
                print(f"  Simulations: {data['simulations']}")
            return True
        else:
            print(f"✗ {name}: HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"✗ {name}: Connection refused (service not running?)")
        return False
    except Exception as e:
        print(f"✗ {name}: {e}")
        return False


def main():
    """Test all services."""
    print("Testing sim2l services...")
    print("=" * 60)

    services = [
        ("Cache Service", "http://localhost:8001"),
        ("Catalog Service", "http://localhost:8002"),
        ("Results Service", "http://localhost:8003"),
    ]

    results = []
    for name, url in services:
        result = test_service(name, url)
        results.append(result)
        print()

    print("=" * 60)
    if all(results):
        print("✓ All services are healthy!")
        return 0
    else:
        print("✗ Some services are not responding")
        print("\nTo start services, run: ./start_services.sh")
        return 1


if __name__ == '__main__':
    sys.exit(main())
