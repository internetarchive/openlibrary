#!/bin/bash

# Test script to verify subjects_json endpoint migration from web.py to FastAPI
# Compares responses from :8080 (web.py) and :18080 (FastAPI)

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

echo -e "${YELLOW}Testing subjects_json endpoint migration${NC}"
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

# Test redirect behavior
test_redirect() {
    local test_name="$1"
    local path="$2"
    local expected_webpy_location="$3"
    local expected_fastapi_location="$4"

    echo -e "${YELLOW}Testing: ${test_name}${NC}"
    echo "  Path: ${path}"
    echo "  Expected web.py redirect to: ${expected_webpy_location}"
    echo "  Expected FastAPI redirect to: ${expected_fastapi_location}"

    local webpy_url="${BASE_WEBPY_URL}${path}"
    local fastapi_url="${BASE_FASTAPI_URL}${path}"

    # Check web.py redirect (get status code and Location header)
    webpy_response=$(curl -s -w "\n%{http_code}\n%{redirect_url}" "${webpy_url}")
    webpy_status=$(echo "$webpy_response" | tail -n2 | head -n1)
    webpy_redirect=$(echo "$webpy_response" | tail -n1)

    # Check FastAPI redirect (get status code and Location header)
    fastapi_response=$(curl -s -w "\n%{http_code}\n%{redirect_url}" "${fastapi_url}")
    fastapi_status=$(echo "$fastapi_response" | tail -n2 | head -n1)
    fastapi_redirect=$(echo "$fastapi_response" | tail -n1)

    # Both should return 301 redirect
    if [ "$webpy_status" != "301" ]; then
        echo -e "  ${RED}✗ web.py didn't return 301, got: ${webpy_status}${NC}"
        return 1
    fi

    if [ "$fastapi_status" != "301" ]; then
        echo -e "  ${RED}✗ FastAPI didn't return 301, got: ${fastapi_status}${NC}"
        return 1
    fi

    # Check redirect URLs match expected (different for web.py vs FastAPI)
    if [[ ! "$webpy_redirect" == *"$expected_webpy_location"* ]]; then
        echo -e "  ${RED}✗ web.py redirect URL mismatch${NC}"
        echo "    Expected to contain: ${expected_webpy_location}"
        echo "    Got: ${webpy_redirect}"
        return 1
    fi

    if [[ ! "$fastapi_redirect" == *"$expected_fastapi_location"* ]]; then
        echo -e "  ${RED}✗ FastAPI redirect URL mismatch${NC}"
        echo "    Expected to contain: ${expected_fastapi_location}"
        echo "    Got: ${fastapi_redirect}"
        return 1
    fi

    echo -e "  ${GREEN}✓ Both return 301 redirect (note: web.py redirects to .json-less URL, FastAPI redirects to .json URL)${NC}"
    echo ""
}

# Test cases
echo "Running test cases..."
echo "====================="
echo ""

# Basic subject query
test_endpoint "Basic subject query" "/subjects/love" ""

# With limit
test_endpoint "With limit" "/subjects/love" "?limit=5"

# With pagination
test_endpoint "With pagination (offset)" "/subjects/love" "?offset=10&limit=5"

# With details
test_endpoint "With details=true" "/subjects/love" "?details=true"

# With has_fulltext
test_endpoint "With has_fulltext=true" "/subjects/love" "?has_fulltext=true"

# With published_in range
test_endpoint "With published_in range" "/subjects/love" "?published_in=2000-2010"

# With published_in year
test_endpoint "With published_in year" "/subjects/love" "?published_in=2000"

# With sort
test_endpoint "With sort=new" "/subjects/love" "?sort=new"

# Person subject
test_endpoint "Person subject" "/subjects/person:mark_twain" ""

# Place subject
test_endpoint "Place subject" "/subjects/place:france" ""

# Subject with spaces (normalized)
test_endpoint "Subject with spaces" "/subjects/science_fiction" ""

# Combined parameters
test_endpoint "Combined parameters" "/subjects/love" "?details=true&has_fulltext=true&limit=3&sort=new"

# Redirect tests
echo "Testing redirect behavior..."
echo "============================="
echo ""

test_redirect "Uppercase to lowercase redirect" "/subjects/LOVE.json" "/subjects/love" "/subjects/love.json"
test_redirect "Mixed case redirect" "/subjects/Science_Fiction.json" "/subjects/science_fiction" "/subjects/science_fiction.json"
test_redirect "Uppercase person redirect" "/subjects/PERSON:MARK_TWAIN.json" "/subjects/person:mark_twain" "/subjects/person:mark_twain.json"

# Error case: excessive limit
echo -e "${YELLOW}Testing: Excessive limit (should return non-200)${NC}"
echo "  Path: /subjects/love"
echo "  Query: ?limit=2001"

webpy_response=$(curl -s -w "\n%{http_code}" "${BASE_WEBPY_URL}/subjects/love.json?limit=2001")
webpy_status=$(echo "$webpy_response" | tail -n1)

fastapi_response=$(curl -s -w "\n%{http_code}" "${BASE_FASTAPI_URL}/subjects/love.json?limit=2001")
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
echo "  curl '${BASE_WEBPY_URL}/subjects/love?details=true' | jq ."
echo "  curl '${BASE_FASTAPI_URL}/subjects/love.json?details=true' | jq ."
