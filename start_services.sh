#!/bin/bash
# Start all sim2l services locally for testing

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting sim2l services...${NC}"

# Create necessary directories
mkdir -p ~/.sim2l/runs
mkdir -p ~/.sim2l/logs

# Stop any existing services
echo -e "${BLUE}Stopping any existing services...${NC}"
pkill -f "sim2l.services.cache_service" 2>/dev/null
pkill -f "sim2l.services.catalog_service" 2>/dev/null
pkill -f "sim2l.services.results_service" 2>/dev/null
sleep 2

# Start Cache Service
echo -e "${BLUE}Starting Cache Service on port 8001...${NC}"
python3 -m sim2l.services.cache_service \
    --backend sqlite \
    --db-path ~/.sim2l/cache.db \
    --no-auth \
    --port 8001 \
    > ~/.sim2l/logs/cache.log 2>&1 &
CACHE_PID=$!
echo -e "${GREEN}Cache Service started (PID: $CACHE_PID)${NC}"

# Wait a bit for service to start
sleep 2

# Start Catalog Service
echo -e "${BLUE}Starting Catalog Service on port 8002...${NC}"
python3 -m sim2l.services.catalog_service \
    --backend sqlite \
    --db-path ~/.sim2l/catalog.db \
    --no-auth \
    --port 8002 \
    > ~/.sim2l/logs/catalog.log 2>&1 &
CATALOG_PID=$!
echo -e "${GREEN}Catalog Service started (PID: $CATALOG_PID)${NC}"

# Wait a bit for service to start
sleep 2

# Start Results Service
echo -e "${BLUE}Starting Results Service on port 8003...${NC}"
python3 -m sim2l.services.results_service \
    --backend sqlite \
    --db-path ~/.sim2l/results.db \
    --no-auth \
    --port 8003 \
    > ~/.sim2l/logs/results.log 2>&1 &
RESULTS_PID=$!
echo -e "${GREEN}Results Service started (PID: $RESULTS_PID)${NC}"

# Wait for all services to be ready
echo -e "${BLUE}Waiting for services to be ready...${NC}"
sleep 3

# Check health of all services
echo -e "${BLUE}Checking service health...${NC}"

check_service() {
    local name=$1
    local port=$2

    if curl -s "http://localhost:$port/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name is healthy${NC}"
        return 0
    else
        echo -e "${RED}✗ $name is not responding${NC}"
        return 1
    fi
}

check_service "Cache Service" 8001
check_service "Catalog Service" 8002
check_service "Results Service" 8003

echo ""
echo -e "${GREEN}All services started!${NC}"
echo ""
echo "Service URLs:"
echo "  Cache Service:   http://localhost:8001"
echo "  Catalog Service: http://localhost:8002"
echo "  Results Service: http://localhost:8003"
echo ""
echo "Logs:"
echo "  Cache:   ~/.sim2l/logs/cache.log"
echo "  Catalog: ~/.sim2l/logs/catalog.log"
echo "  Results: ~/.sim2l/logs/results.log"
echo ""
echo "To stop services, run: ./stop_services.sh"
echo "To view logs: tail -f ~/.sim2l/logs/*.log"
echo ""
echo "Auth mode: disabled (--no-auth) for local UI development"
