#!/usr/bin/env python3
"""
Interactive web-ui test script.

Starts the Vite dev server, opens each page in the browser, and asks the user
to confirm what they see. No backend services required — the UI degrades
gracefully when they are offline.

Usage:
    python3 tests/manual/ui_interactive_check.py
"""

import subprocess
import sys
import time
import webbrowser
import signal
from pathlib import Path

BASE_URL = "http://localhost:3000"
WEB_UI_DIR = Path(__file__).resolve().parents[2] / "web-ui"

PAGES = [
    {
        "name": "Dashboard",
        "url": f"{BASE_URL}/",
        "checks": [
            "The page title 'sim2l Dashboard' is visible in the header",
            "There is a 'Service Health' section with Cache, Results, and Catalog cards",
            "Each service card shows a status chip (Healthy or Unhealthy)",
            "There is an 'Overview Statistics' section with 4 stat cards",
        ],
    },
    {
        "name": "Cache",
        "url": f"{BASE_URL}/cache",
        "checks": [
            "The Cache page loads without a blank screen or error",
            "There is a search/filter area at the top",
            "There is a table or empty-state message for cache entries",
        ],
    },
    {
        "name": "Results",
        "url": f"{BASE_URL}/results",
        "checks": [
            "The Results page loads without a blank screen or error",
            "There are filter inputs (simulation name, version, status)",
            "There is a results table or empty-state message",
        ],
    },
    {
        "name": "Catalog",
        "url": f"{BASE_URL}/catalog",
        "checks": [
            "The Catalog page loads without a blank screen or error",
            "There is a search input for simulations",
            "There is a table or empty-state message for simulations",
        ],
    },
]

# ANSI colours
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def ask(question: str) -> bool:
    """Prompt the user for a yes/no answer. Returns True for yes."""
    while True:
        sys.stdout.write(f"  {question} {BOLD}[y/n]{RESET} ")
        sys.stdout.flush()
        answer = sys.stdin.readline().strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please enter y or n.", flush=True)


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait until the dev server responds."""
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def run():
    results = {}

    print(f"\n{BOLD}sim2l Web-UI Interactive Test{RESET}")
    print("=" * 50)

    # Start Vite dev server
    print(f"\n{YELLOW}Starting Vite dev server...{RESET}")
    dev_server = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(WEB_UI_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def cleanup(sig=None, frame=None):
        print(f"\n{YELLOW}Stopping dev server...{RESET}")
        dev_server.terminate()
        try:
            dev_server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            dev_server.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    if not wait_for_server(BASE_URL):
        print(f"{RED}Dev server did not start within 30s. Is port 3000 free?{RESET}")
        cleanup()

    print(f"{GREEN}Dev server is up at {BASE_URL}{RESET}")
    print(f"\n{YELLOW}Note:{RESET} Backend services (cache/results/catalog) may not be running.")
    print("      The UI should still load and show service cards as 'Unhealthy'.")

    # Run through each page
    for page in PAGES:
        print(f"\n{'─' * 50}")
        print(f"{BOLD}Page: {page['name']}{RESET}  →  {page['url']}")
        print(f"{'─' * 50}")

        sys.stdout.write(f"  Press {BOLD}Enter{RESET} to open {page['name']} in the browser...")
        sys.stdout.flush()
        sys.stdin.readline()
        webbrowser.open(page["url"])
        time.sleep(1.5)  # Give the browser a moment to load

        page_passed = True
        for check in page["checks"]:
            ok = ask(f"✓ {check}?")
            if not ok:
                page_passed = False

        results[page["name"]] = page_passed
        status = f"{GREEN}PASS{RESET}" if page_passed else f"{RED}FAIL{RESET}"
        print(f"\n  {page['name']}: {status}")

    # Summary
    print(f"\n{'=' * 50}")
    print(f"{BOLD}Summary{RESET}")
    print(f"{'=' * 50}")
    all_passed = True
    for name, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {name:<12} {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print(f"{GREEN}{BOLD}All pages passed.{RESET}")
    else:
        print(f"{RED}{BOLD}Some pages failed. Review the items marked FAIL above.{RESET}")

    cleanup()


if __name__ == "__main__":
    run()
