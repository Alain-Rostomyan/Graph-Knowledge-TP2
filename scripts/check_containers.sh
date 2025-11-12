#!/bin/bash
set -e

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Determine if running in container or local
MODE=${1:-local}

if [ "$MODE" = "container" ]; then
    # Running inside container
    API_HOST="app"
    POSTGRES_HOST="postgres"
else
    # Running locally
    API_HOST="127.0.0.1"
    POSTGRES_HOST="localhost"
fi

echo -e "${BLUE}Running health checks in $MODE mode...${NC}\n"

# 1. Check FastAPI health endpoint
echo -e "${BLUE}› FastAPI health check${NC}"
HEALTH_RESPONSE=$(curl -s http://${API_HOST}:8000/health)
if echo "$HEALTH_RESPONSE" | grep -q '"ok":true'; then
    echo -e "${GREEN}✔ FastAPI health OK${NC}"
    echo "$HEALTH_RESPONSE"
else
    echo -e "${RED}✘ FastAPI health check failed${NC}"
    echo "$HEALTH_RESPONSE"
    exit 1
fi

echo ""

# 2. Check Postgres - list orders
echo -e "${BLUE}› Postgres: SELECT * FROM orders LIMIT 5;${NC}"
if [ "$MODE" = "container" ]; then
    PGPASSWORD=${POSTGRES_PASSWORD:-password} psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER:-app} -d ${POSTGRES_DB:-shop} -c "SELECT * FROM orders LIMIT 5;"
else
    docker compose exec -T postgres psql -U app -d shop -c "SELECT * FROM orders LIMIT 5;"
fi

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✔ Orders query OK${NC}\n"
else
    echo -e "${RED}✘ Orders query failed${NC}"
    exit 1
fi

# 3. Check Postgres - current time
echo -e "${BLUE}› Postgres: SELECT now();${NC}"
if [ "$MODE" = "container" ]; then
    PGPASSWORD=${POSTGRES_PASSWORD:-password} psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER:-app} -d ${POSTGRES_DB:-shop} -c "SELECT now();"
else
    docker compose exec -T postgres psql -U app -d shop -c "SELECT now();"
fi

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✔ now() query OK${NC}\n"
else
    echo -e "${RED}✘ now() query failed${NC}"
    exit 1
fi

# 4. Run ETL script
echo -e "${BLUE}› ETL: python /work/app/etl.py${NC}"
if [ "$MODE" = "container" ]; then
    cd /work/app
    pip install -q -r requirements.txt
    ETL_OUTPUT=$(python etl.py 2>&1)
else
    ETL_OUTPUT=$(docker compose exec -T app python /work/app/etl.py 2>&1 | cat)
fi

echo "$ETL_OUTPUT"

if echo "$ETL_OUTPUT" | grep -q "ETL done."; then
    echo -e "${GREEN}✔ ETL output OK (ETL done.)${NC}"
else
    echo -e "${RED}✘ ETL did not complete successfully${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}All checks passed!${NC}"
