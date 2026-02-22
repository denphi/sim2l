#!/bin/bash
# Run the complete sim2l workflow example
#
# This script:
# 1. Checks if services are running
# 2. Offers to start them if needed
# 3. Runs the complete workflow example
# 4. Optionally stops services afterward

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "                   SIM2L COMPLETE WORKFLOW RUNNER"
echo "========================================================================"

# Function to check if a service is running
check_service() {
    local port=$1
    local name=$2

    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health | grep -q "200"; then
        echo -e "${GREEN}✓${NC} $name service is running on port $port"
        return 0
    else
        echo -e "${RED}✗${NC} $name service is NOT running on port $port"
        return 1
    fi
}

# Check if all services are running
echo -e "\nChecking service status..."
CACHE_RUNNING=0
CATALOG_RUNNING=0
RESULTS_RUNNING=0

check_service 8001 "Cache" && CACHE_RUNNING=1 || true
check_service 8002 "Catalog" && CATALOG_RUNNING=1 || true
check_service 8003 "Results" && RESULTS_RUNNING=1 || true

ALL_RUNNING=$((CACHE_RUNNING && CATALOG_RUNNING && RESULTS_RUNNING))

if [ $ALL_RUNNING -eq 1 ]; then
    echo -e "\n${GREEN}All services are running!${NC}"
    SERVICES_STARTED_BY_SCRIPT=0
else
    echo -e "\n${YELLOW}Some services are not running.${NC}"
    echo -e "The workflow example will start services automatically."
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
    SERVICES_STARTED_BY_SCRIPT=1
fi

# Run the complete workflow example
echo -e "\n========================================================================"
echo "                    RUNNING WORKFLOW EXAMPLE"
echo "========================================================================"

cd "$(dirname "$0")/.." || exit 1

python3 examples/complete_workflow_example.py

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✓ Workflow completed successfully!${NC}"
else
    echo -e "\n${RED}✗ Workflow failed with exit code $EXIT_CODE${NC}"
    exit $EXIT_CODE
fi

# If we started services, they're already stopped by the script
# If services were already running, leave them running

echo -e "\n========================================================================"
echo "                         EXAMPLE COMPLETE"
echo "========================================================================"
echo ""
echo "Next steps:"
echo "  - Review the output above to understand the workflow"
echo "  - Try the quick start: python3 examples/quick_start_example.py"
echo "  - Explore databases: sqlite3 ~/.sim2l/*.db"
echo "  - Read the examples: ls examples/*.py"
echo ""
