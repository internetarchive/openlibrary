#!/bin/bash
# Test script to compare browse endpoints between web.py and FastAPI
# TODO: DELETE BEFORE MERGING, ONLY NEEDED FOR COMPARISON TESTING

BASE_WEB="http://localhost:8080"
BASE_FASTAPI="http://localhost:18080"

echo "=== Browse Endpoint Comparison Test ==="

PASSED=0
FAILED=0

#######################################
# GET ENDPOINT TESTS
#######################################
echo ""
echo "===== GET ENDPOINT TESTS ====="

run_test() {
    local test_name="$1"
    local query_string="$2"
    
    echo ""
    echo "=== $test_name ==="
    
    echo "Web.py:"
    WEB_RESP=$(curl -s "$BASE_WEB/browse.json$query_string" -w "\nStatus:%{http_code}")
    WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
    WEB_BODY=$(echo "$WEB_RESP" | grep -v Status)
    echo "Code: $WEB_CODE"
    
    echo "FastAPI:"
    FASTAPI_RESP=$(curl -s "$BASE_FASTAPI/browse$query_string" -w "\nStatus:%{http_code}")
    FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
    FASTAPI_BODY=$(echo "$FASTAPI_RESP" | grep -v Status)
    echo "Code: $FASTAPI_CODE"
    
    WEB_NORM=$(echo "$WEB_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
    FASTAPI_NORM=$(echo "$FASTAPI_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
    
    if [ "$WEB_CODE" = "$FASTAPI_CODE" ] && [ "$WEB_NORM" = "$FASTAPI_NORM" ]; then
        echo "PASS"
        ((PASSED++))
    else
        echo "FAIL"
        echo "Web Body: $WEB_NORM"
        echo "FastAPI Body: $FASTAPI_NORM"
        ((FAILED++))
    fi
}

# Test 1: Default parameters
run_test "Test 1: Default browse parameters (200)" ""

# Test 2: Standard text query
run_test "Test 2: Query 'tolkien' (200)" "?q=tolkien"

# Test 3: Pagination and limits
run_test "Test 3: Limit 5, Page 2 (200)" "?q=harry&limit=5&page=2"

# Test 4: Subject and sorts
run_test "Test 4: Subject 'romance', sorts 'new' (200)" "?subject=romance&sorts=new"

# Test 5: Multiple sorts
run_test "Test 5: Multiple sorts (200)" "?q=magic&sorts=new,title"

# Test 6: Invalid types (FastAPI 422 vs Web.py 500)
echo ""
echo "=== Test 6: Invalid limit type (500 vs 422) ==="
echo "Web.py:"
WEB_RESP=$(curl -s "$BASE_WEB/browse.json?limit=abc" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s "$BASE_FASTAPI/browse?limit=abc" -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "500" ] && [ "$FASTAPI_CODE" = "422" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

echo ""
echo "=== Summary ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""


echo "Test URLs used:"
echo "  GET  $BASE_WEB/browse.json"
echo "  GET  $BASE_FASTAPI/browse"

if [ $FAILED -gt 0 ]; then
    exit 1
fi

echo ""
echo "All tests passed!"