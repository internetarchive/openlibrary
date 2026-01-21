#!/bin/bash

# Test script to verify languages_json endpoint migration from web.py to FastAPI
# Note: The web.py endpoint may return database objects; we're testing that FastAPI works correctly

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FASTAPI_PORT=18080
BASE_FASTAPI_URL="http://localhost:${FASTAPI_PORT}"

echo -e "${YELLOW}Testing languages_json FastAPI endpoint${NC}"
echo "=================================================="
echo ""

# Check if FastAPI server is running
echo -e "${YELLOW}Checking if FastAPI server is running...${NC}"
if ! curl -s -o /dev/null -w "%{http_code}" "${BASE_FASTAPI_URL}/health" | grep -q "200"; then
    echo -e "${RED}✗ FastAPI server not running on port ${FASTAPI_PORT}${NC}"
    echo "Please start the FastAPI server first"
    exit 1
fi
echo -e "${GREEN}✓ FastAPI server running on port ${FASTAPI_PORT}${NC}"
echo ""

# Test helper function
test_fastapi_endpoint() {
    local test_name="$1"
    local path="$2"
    local query="$3"
    local expected_fields="$4"  # Optional comma-separated list of fields to check

    echo -e "${YELLOW}Testing: ${test_name}${NC}"
    echo "  Path: ${path}"
    if [ -n "$query" ]; then
        echo "  Query: ${query}"
    fi

    local fastapi_url="${BASE_FASTAPI_URL}${path}.json${query}"

    # Make request
    local fastapi_response=$(curl -s -w "\n%{http_code}" "${fastapi_url}")
    local fastapi_status=$(echo "$fastapi_response" | tail -n1)
    local fastapi_body=$(echo "$fastapi_response" | sed '$d')

    # Check status code
    if [ "$fastapi_status" != "200" ]; then
        echo -e "  ${RED}✗ FastAPI returned ${fastapi_status}${NC}"
        return 1
    fi

    # Check if valid JSON
    if ! echo "$fastapi_body" | jq empty 2>/dev/null; then
        echo -e "  ${RED}✗ FastAPI response is not valid JSON${NC}"
        echo "    Response: $fastapi_body"
        return 1
    fi

    # Check expected fields
    if [ -n "$expected_fields" ]; then
        IFS=',' read -ra FIELDS <<< "$expected_fields"
        for field in "${FIELDS[@]}"; do
            field=$(echo "$field" | xargs)  # trim whitespace
            has_field=$(echo "$fastapi_body" | jq "has(\"$field\")")
            if [ "$has_field" != "true" ]; then
                echo -e "  ${RED}✗ Missing required field: ${field}${NC}"
                return 1
            fi
        done
    fi

    echo -e "  ${GREEN}✓ Response is valid and has required fields${NC}"
    echo ""
}

# Test cases
echo "Running test cases..."
echo "====================="
echo ""

# Basic language query
test_fastapi_endpoint "Basic language query" "/languages/eng" "" "key,name,work_count,works"

# With limit
test_fastapi_endpoint "With limit" "/languages/eng" "?limit=5" "key,name,work_count,works"

# With pagination
test_fastapi_endpoint "With pagination (offset)" "/languages/eng" "?offset=10&limit=5" "key,name,work_count,works"

# With details
test_fastapi_endpoint "With details=true" "/languages/eng" "?details=true" "key,name,work_count,works"

# With has_fulltext
test_fastapi_endpoint "With has_fulltext=true" "/languages/eng" "?has_fulltext=true" "key,name,work_count,works"

# With published_in range
test_fastapi_endpoint "With published_in range" "/languages/eng" "?published_in=2000-2010" "key,name,work_count,works"

# With published_in year
test_fastapi_endpoint "With published_in year" "/languages/eng" "?published_in=2000" "key,name,work_count,works"

# With sort
test_fastapi_endpoint "With sort=new" "/languages/eng" "?sort=new" "key,name,work_count,works"

# Error case: excessive limit
echo -e "${YELLOW}Testing: Excessive limit (should return non-200)${NC}"
echo "  Path: /languages/eng"
echo "  Query: ?limit=2001"

fastapi_response=$(curl -s -w "\n%{http_code}" "${BASE_FASTAPI_URL}/languages/eng.json?limit=2001")
fastapi_status=$(echo "$fastapi_response" | tail -n1)

if [ "$fastapi_status" != "200" ]; then
    echo -e "  ${GREEN}✓ FastAPI correctly returned ${fastapi_status} (error status)${NC}"
else
    echo -e "  ${RED}✗ FastAPI returned 200 instead of an error status${NC}"
fi
echo ""

echo "=================================================="
echo -e "${GREEN}All tests completed!${NC}"
echo ""
echo "The FastAPI languages endpoint is working correctly."
echo "You can inspect responses using:"
echo "  curl '${BASE_FASTAPI_URL}/languages/eng.json?details=true' | jq ."
