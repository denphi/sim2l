#!/bin/bash
# Stop all sim2l services

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${BLUE}Stopping sim2l services...${NC}"

# Stop services
pkill -f "sim2l.services.cache_service"
pkill -f "sim2l.services.catalog_service"
pkill -f "sim2l.services.results_service"

sleep 2

echo -e "${GREEN}All services stopped${NC}"
