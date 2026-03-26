#!/bin/bash
# ==========================================
# Health Check Script for BunkerM Extended
# ==========================================
# Usage: ./scripts/check-health.sh

set -e

echo "=========================================="
echo "BunkerM Extended - Health Check"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables
if [ -f .env.dev ]; then
    set -a
    source .env.dev
    set +a
else
    echo -e "${RED}[ERROR] .env.dev file not found${NC}"
    exit 1
fi

# Function to check service health
check_service() {
    local service_name=$1
    local url=$2
    local expected_code=${3:-200}
    
    echo -n "Checking $service_name... "
    
    if response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null); then
        if [ "$response" = "$expected_code" ]; then
            echo -e "${GREEN}[OK]${NC} (HTTP $response)"
            return 0
        else
            echo -e "${YELLOW}[WARNING]${NC} (HTTP $response, expected $expected_code)"
            return 1
        fi
    else
        echo -e "${RED}[FAILED]${NC} (unreachable)"
        return 1
    fi
}

# Function to check Docker container
check_container() {
    local container_name=$1
    
    echo -n "Checking container $container_name... "
    
    if ${CE:-docker} ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        local status=$(${CE:-docker} inspect -f '{{.State.Status}}' "$container_name")
        if [ "$status" = "running" ]; then
            echo -e "${GREEN}[OK] Running${NC}"
            return 0
        else
            echo -e "${RED}[ERROR] Status: $status${NC}"
            return 1
        fi
    else
        echo -e "${RED}[ERROR] Not found${NC}"
        return  1
    fi
}

# Function to check PostgreSQL
check_postgres() {
    echo -n "Checking PostgreSQL connection... "
    
    if ${CE:-docker} exec bunkerm-postgres pg_isready -U ${POSTGRES_USER:-bunkerm} -d ${POSTGRES_DB:-bunkerm_db} > /dev/null 2>&1; then
        echo -e "${GREEN}[OK] Connected${NC}"
        return 0
    else
        echo -e "${RED}[ERROR] Connection failed${NC}"
        return 1
    fi
}

# Function to check Mosquitto
check_mosquitto() {
    echo -n "Checking Mosquitto MQTT broker... "
    
    if ${CE:-docker} exec bunkerm-mosquitto mosquitto_sub -t '$SYS/#' -C 1 -W 3 > /dev/null 2>&1; then
        echo -e "${GREEN}[OK] Responding${NC}"
        return 0
    else
        echo -e "${RED}[ERROR] Not responding${NC}"
        return 1
    fi
}

echo "1. Docker Containers"
echo "--------------------"
check_container "bunkerm-postgres"
check_container "bunkerm-mosquitto"
check_container "bunkerm-nginx"
# check_container "bunkerm-backend"
# check_container "bunkerm-frontend"

echo ""
echo "2. Service Connectivity"
echo "-----------------------"
check_postgres
check_mosquitto

echo ""
echo "3. HTTP Endpoints"
echo "-----------------"
check_service "Nginx (Web UI)" "http://localhost:${NGINX_PORT:-2000}/" 200
check_service "Nginx Health" "http://localhost:${NGINX_PORT:-2000}/health" 200

# Uncomment when backend services are running
# check_service "Backend API" "http://localhost:${NGINX_PORT:-2000}/api/health" 200
# check_service "Smart Anomaly Service" "http://localhost:${SMART_ANOMALY_PORT:-8100}/health" 200

echo ""
echo "4. Port Availability"
echo "--------------------"

check_port() {
    local port=$1
    local service=$2
    
    echo -n "Port $port ($service)... "
    
    if netstat -an 2>/dev/null | grep -q ":$port .*LISTEN" || \
       ss -tuln 2>/dev/null | grep -q ":$port "; then
        echo -e "${GREEN}[OK] Listening${NC}"
        return 0
    else
        echo -e "${RED}[ERROR] Not listening${NC}"
        return 1
    fi
}

check_port "${POSTGRES_PORT:-5432}" "PostgreSQL"
check_port "${MQTT_PORT:-1900}" "Mosquitto MQTT"
check_port "${MQTT_WS_PORT:-9001}" "Mosquitto WebSocket"
check_port "${NGINX_PORT:-2000}" "Nginx"

echo ""
echo "=========================================="
echo "Health Check Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. If all checks passed: [OK] Environment is ready!"
echo "2. If PostgreSQL failed: Check logs with 'docker-compose logs postgres'"
echo "3. If Mosquitto failed: Check logs with 'docker-compose logs mosquitto'"
echo "4. Access UI at: http://localhost:${NGINX_PORT:-2000}"
echo "5. Access pgAdmin at: http://localhost:${PGADMIN_PORT:-5050} (with --profile tools)"
echo ""
