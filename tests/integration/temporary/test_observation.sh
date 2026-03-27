#!/bin/bash
# Test script to compare public_observations endpoints between web.py and FastAPI
# TODO: DELETE BEFORE MERGING, ONLY NEEDED FOR COMPARISON TESTING

BASE_WEB="http://localhost:8080"
BASE_FASTAPI="http://localhost:18080"

echo "=== Public Observations Endpoint Comparison Test ==="
PASSED=0
FAILED=0

echo ""
echo "===== GET ENDPOINT TESTS ====="

run_test() {
    local test_name="$1"
    local query_string="$2"
    
    echo ""
    echo "=== $test_name ==="
    
    echo "Web.py:"
    WEB_RESP=$(curl -s "$BASE_WEB/observations.json$query_string" -w "\nStatus:%{http_code}")
    WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
    WEB_BODY=$(echo "$WEB_RESP" | grep -v Status)
    echo "Code: $WEB_CODE"
    
    echo "FastAPI:"
    FASTAPI_RESP=$(curl -s "$BASE_FASTAPI/observations.json$query_string" -w "\nStatus:%{http_code}")
    FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
    FASTAPI_BODY=$(echo "$FASTAPI_RESP" | grep -v Status)
    echo "Code: $FASTAPI_CODE"

    if [ "$WEB_CODE" != "$FASTAPI_CODE" ]; then
        echo "FAIL - Status codes do not match!"
        ((FAILED++))
        return
    fi

    if [ "$WEB_CODE" != "200" ]; then
        echo "PASS (Both endpoints returned HTTP $WEB_CODE)"
        ((PASSED++))
        return
    fi

    WEB_NORM=$(echo "$WEB_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
    FASTAPI_NORM=$(echo "$FASTAPI_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
    
    if [ "$WEB_NORM" = "$FASTAPI_NORM" ]; then
        echo "PASS"
        ((PASSED++))
    else
        echo "FAIL - JSON bodies do not match"
        echo "Web Body: $WEB_NORM"
        echo "FastAPI Body: $FASTAPI_NORM"
        ((FAILED++))
    fi
}

run_test "Test 1: Empty request (No OLIDs)" ""

run_test "Test 2: Single OLID (OL27448W)" "?olid=OL27448W"

run_test "Test 3: Multiple OLIDs (OL27448W & OL24204W)" "?olid=OL27448W&olid=OL24204W"

run_test "Test 4: Invalid OLID string" "?olid=hehe"

echo ""
echo "=== Summary ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""
echo "Test URLs used:"
echo "  GET  $BASE_WEB/observations.json"
echo "  GET  $BASE_FASTAPI/observations.json"

if [ $FAILED -gt 0 ]; then
    echo "FAILED."
    exit 1
fi

echo ""
echo " All tests passed!"