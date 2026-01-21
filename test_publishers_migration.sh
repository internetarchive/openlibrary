#!/bin/bash

# Test script to verify publishers_json endpoint migration from web.py to FastAPI
# Compares responses from old web.py (:8080) vs new FastAPI (:18080)

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

WEBPY_PORT=8080
FASTAPI_PORT=18080
BASE_WEBPY_URL="http://localhost:${WEBPY_PORT}"
BASE_FASTAPI_URL="http://localhost:${FASTAPI_PORT}"

echo -e "${YELLOW}Testing publishers_json endpoint migration${NC}"
echo "=================================================="
echo ""

# Check if servers are running
echo -e "${YELLOW}Checking if servers are running...${NC}"
if ! curl -s -o /dev/null -w "%{http_code}" "${BASE_WEBPY_URL}/" | grep -q "200\|404"; then
    echo -e "${RED}✗ web.py server not running on port ${WEBPY_PORT}${NC}"
    echo "Please start the web.py server first"
    exit 1
fi
echo -e "${GREEN}✓ web.py server running on port ${WEBPY_PORT}${NC}"

if ! curl -s -o /dev/null -w "%{http_code}" "${BASE_FASTAPI_URL}/health" | grep -q "200"; then
    echo -e "${RED}✗ FastAPI server not running on port ${FASTAPI_PORT}${NC}"
    echo "Please start the FastAPI server first"
    exit 1
fi
echo -e "${GREEN}✓ FastAPI server running on port ${FASTAPI_PORT}${NC}"
echo ""

# Test helper function
test_endpoint() {
    local test_name="$1"
    local path="$2"
    local query="$3"

    echo -e "${YELLOW}Testing: ${test_name}${NC}"
    echo "  Path: ${path}"
    if [ -n "$query" ]; then
        echo "  Query: ${query}"
    fi

    local webpy_url="${BASE_WEBPY_URL}${path}.json${query}"
    local fastapi_url="${BASE_FASTAPI_URL}${path}.json${query}"

    # Make requests
    local webpy_response=$(curl -s -w "\n%{http_code}" "${webpy_url}")
    local webpy_status=$(echo "$webpy_response" | tail -n1)
    local webpy_body=$(echo "$webpy_response" | sed '$d')

    local fastapi_response=$(curl -s -w "\n%{http_code}" "${fastapi_url}")
    local fastapi_status=$(echo "$fastapi_response" | tail -n1)
    local fastapi_body=$(echo "$fastapi_response" | sed '$d')

    # Compare status codes
    if [ "$webpy_status" != "$fastapi_status" ]; then
        echo -e "  ${RED}✗ Status code mismatch: webpy=${webpy_status}, fastapi=${fastapi_status}${NC}"
        return 1
    fi

    # For 200 responses, compare JSON structure
    if [ "$webpy_status" = "200" ]; then
        # Check if both are valid JSON
        if ! echo "$webpy_body" | jq empty 2>/dev/null; then
            echo -e "  ${RED}✗ web.py response is not valid JSON${NC}"
            return 1
        fi
        if ! echo "$fastapi_body" | jq empty 2>/dev/null; then
            echo -e "  ${RED}✗ FastAPI response is not valid JSON${NC}"
            return 1
        fi

        # Compare top-level keys
        webpy_keys=$(echo "$webpy_body" | jq 'keys' | sort)
        fastapi_keys=$(echo "$fastapi_body" | jq 'keys' | sort)

        if [ "$webpy_keys" != "$fastapi_keys" ]; then
            echo -e "  ${RED}✗ Top-level keys mismatch${NC}"
            echo "    webpy: ${webpy_keys}"
            echo "    fastapi: ${fastapi_keys}"
            return 1
        fi

        # Check common required fields
        for field in "key" "name" "work_count" "works"; do
            webpy_has=$(echo "$webpy_body" | jq "has(\"${field}\")")
            fastapi_has=$(echo "$fastapi_body" | jq "has(\"${field}\")")
            if [ "$webpy_has" != "$fastapi_has" ]; then
                echo -e "  ${RED}✗ Field '${field}' presence mismatch${NC}"
                return 1
            fi
        done

        echo -e "  ${GREEN}✓ Response structures match${NC}"
    else
        echo -e "  ${GREEN}✓ Both returned ${webpy_status}${NC}"
    fi
    echo ""
}

# Test cases
echo "Running test cases..."
echo "====================="
echo ""

# Basic publisher query (underscores get replaced with spaces)
test_endpoint "Basic publisher query" "/publishers/Penguin_Books" ""

# With limit
test_endpoint "With limit" "/publishers/Penguin_Books" "?limit=5"

# With pagination
test_endpoint "With pagination (offset)" "/publishers/Penguin_Books" "?offset=10&limit=5"

# With details
test_endpoint "With details=true" "/publishers/Penguin_Books" "?details=true"

# With has_fulltext
test_endpoint "With has_fulltext=true" "/publishers/Penguin_Books" "?has_fulltext=true"

# With published_in range
test_endpoint "With published_in range" "/publishers/Penguin_Books" "?published_in=2000-2010"

# With published_in year
test_endpoint "With published_in year" "/publishers/Penguin_Books" "?published_in=2000"

# With sort
test_endpoint "With sort=new" "/publishers/Penguin_Books" "?sort=new"

# Error case: excessive limit
echo -e "${YELLOW}Testing: Excessive limit (should return non-200)${NC}"
echo "  Path: /publishers/Penguin_Books"
echo "  Query: ?limit=2001"

webpy_response=$(curl -s -w "\n%{http_code}" "${BASE_WEBPY_URL}/publishers/Penguin_Books.json?limit=2001")
webpy_status=$(echo "$webpy_response" | tail -n1)

fastapi_response=$(curl -s -w "\n%{http_code}" "${BASE_FASTAPI_URL}/publishers/Penguin_Books.json?limit=2001")
fastapi_status=$(echo "$fastapi_response" | tail -n1)

if [ "$webpy_status" != "200" ] && [ "$fastapi_status" != "200" ]; then
    echo -e "  ${GREEN}✓ Both correctly returned error statuses (webpy=${webpy_status}, fastapi=${fastapi_status})${NC}"
else
    echo -e "  ${RED}✗ One or both returned 200: webpy=${webpy_status}, fastapi=${fastapi_status}${NC}"
fi
echo ""

echo "=================================================="
echo -e "${GREEN}All tests completed!${NC}"
echo ""
echo "If all tests passed, the FastAPI endpoint is working correctly."
echo "You can now compare individual responses using:"
echo "  curl '${BASE_WEBPY_URL}/publishers/Penguin_Books.json?details=true' | jq ."
echo "  curl '${BASE_FASTAPI_URL}/publishers/Penguin_Books.json?details=true' | jq ."
