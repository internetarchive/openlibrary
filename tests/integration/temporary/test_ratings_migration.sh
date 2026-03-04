#!/bin/bash
# Test script to compare ratings endpoints between web.py and FastAPI
# TODO: DELETE BEFORE MERGING, ONLY NEEDED FOR COMPARISON TESTING

set -e

BASE_WEB="http://localhost:8080"
BASE_FASTAPI="http://localhost:18080"
USERNAME="openlibrary@example.com"
PASSWORD="admin123"

echo "=== Ratings Endpoint Comparison Test ==="

# Create a session
echo "Logging in..."
LOGIN_RESP=$(curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt -X POST "$BASE_WEB/account/login" \
  -d "username=$USERNAME&password=$PASSWORD&remember=true" -w "\n%{http_code}" -L)

SESSION=$(grep session /tmp/cookies.txt | awk '{print $7}')

if [ -z "$SESSION" ]; then
    echo "ERROR: Failed to get session cookie"
    exit 1
fi

echo "Session: ${SESSION:0:20}..."

PASSED=0
FAILED=0

#######################################
# GET ENDPOINT TESTS
#######################################

echo ""
echo "===== GET ENDPOINT TESTS ====="

# Test 1: GET ratings for an existing work
echo ""
echo "=== Test 1: GET ratings (200) ==="
echo "Web.py:"
WEB_RESP=$(curl -s "$BASE_WEB/works/OL45883W/ratings.json" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
WEB_BODY=$(echo "$WEB_RESP" | grep -v Status)
echo "Code: $WEB_CODE"
echo "Body: $WEB_BODY"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s "$BASE_FASTAPI/works/OL45883W/ratings" -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
FASTAPI_BODY=$(echo "$FASTAPI_RESP" | grep -v Status)
echo "Code: $FASTAPI_CODE"
echo "Body: $FASTAPI_BODY"

# Normalize JSON for comparison (handles whitespace differences)
WEB_NORM=$(echo "$WEB_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
FASTAPI_NORM=$(echo "$FASTAPI_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")

if [ "$WEB_CODE" = "$FASTAPI_CODE" ] && [ "$WEB_NORM" = "$FASTAPI_NORM" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 2: GET ratings for non-existent work (should return empty summary)
echo ""
echo "=== Test 2: GET ratings non-existent work (200, empty) ==="
echo "Web.py:"
WEB_RESP=$(curl -s "$BASE_WEB/works/OL99999999W/ratings.json" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
WEB_BODY=$(echo "$WEB_RESP" | grep -v Status)
echo "Code: $WEB_CODE"
echo "Body: $WEB_BODY"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s "$BASE_FASTAPI/works/OL99999999W/ratings" -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
FASTAPI_BODY=$(echo "$FASTAPI_RESP" | grep -v Status)
echo "Code: $FASTAPI_CODE"
echo "Body: $FASTAPI_BODY"

# Normalize JSON for comparison
WEB_NORM=$(echo "$WEB_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
FASTAPI_NORM=$(echo "$FASTAPI_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")

if [ "$WEB_CODE" = "$FASTAPI_CODE" ] && [ "$WEB_NORM" = "$FASTAPI_NORM" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

#######################################
# POST ENDPOINT TESTS
#######################################

echo ""
echo "===== POST ENDPOINT TESTS ====="

# Test 3: POST add valid rating (200)
echo ""
echo "=== Test 3: POST add rating (200) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/ratings.json" \
    -d "rating=4" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
WEB_BODY=$(echo "$WEB_RESP" | grep -v Status)
echo "Code: $WEB_CODE"
echo "Body: $WEB_BODY"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/ratings" \
    -H "Content-Type: application/json" \
    -d '{"rating": 4}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
FASTAPI_BODY=$(echo "$FASTAPI_RESP" | grep -v Status)
echo "Code: $FASTAPI_CODE"
echo "Body: $FASTAPI_BODY"

WEB_NORM=$(echo "$WEB_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
FASTAPI_NORM=$(echo "$FASTAPI_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")

if [ "$WEB_CODE" = "$FASTAPI_CODE" ] && [ "$WEB_NORM" = "$FASTAPI_NORM" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 4: POST add rating with edition_id (200)
echo ""
echo "=== Test 4: POST add rating with edition_id (200) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/ratings.json" \
    -d "rating=5&edition_id=OL1M" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/ratings" \
    -H "Content-Type: application/json" \
    -d '{"rating": 5, "edition_id": "OL1M"}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 5: POST remove rating (200)
echo ""
echo "=== Test 5: POST remove rating (200) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/ratings.json" \
    -d "" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/ratings" \
    -H "Content-Type: application/json" \
    -d '{}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 6: POST invalid rating (200 vs 422)
echo ""
echo "=== Test 6: POST invalid rating (200 vs 422) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/ratings.json" \
    -d "rating=10" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
WEB_BODY=$(echo "$WEB_RESP" | grep -v Status)
echo "Code: $WEB_CODE"
echo "Body: $WEB_BODY"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/ratings" \
    -H "Content-Type: application/json" \
    -d '{"rating": 10}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
FASTAPI_BODY=$(echo "$FASTAPI_RESP" | grep -v Status)
echo "Code: $FASTAPI_CODE"
echo "Body: $FASTAPI_BODY"

# Accept both 200 (web.py with error JSON) and 422 (FastAPI validation)
if [ "$WEB_CODE" = "$FASTAPI_CODE" ] || [ "$FASTAPI_CODE" = "422" ]; then
    echo "PASS (known difference: legacy 200+{error} vs fastapi 422)"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 7: POST unauthenticated (302/303 vs 401)
echo ""
echo "=== Test 7: POST unauthenticated (redirect vs 401) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -X POST "$BASE_WEB/works/OL45883W/ratings.json" \
    -d "rating=3" -w "\nStatus:%{http_code}" -o /dev/null)
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -X POST "$BASE_FASTAPI/works/OL45883W/ratings" \
    -H "Content-Type: application/json" \
    -d '{"rating": 3}' -w "\nStatus:%{http_code}" -o /dev/null)
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

# Known difference: legacy redirects (302/303), FastAPI returns 401
if ([ "$WEB_CODE" = "302" ] || [ "$WEB_CODE" = "303" ]) && [ "$FASTAPI_CODE" = "401" ]; then
    echo "PASS (known difference: legacy redirects, fastapi returns 401)"
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
echo "Known acceptable differences:"
echo "  - Auth: legacy redirects to /account/login vs fastapi returns 401"
echo "  - Invalid rating: legacy 200 + {error: invalid rating} vs fastapi 422"

echo ""
echo "Test URLs used:"
echo "  GET  $BASE_WEB/works/OL45883W/ratings.json"
echo "  GET  $BASE_FASTAPI/works/OL45883W/ratings"
echo "  POST $BASE_WEB/works/OL45883W/ratings"
echo "  POST $BASE_FASTAPI/works/OL45883W/ratings"

if [ $FAILED -gt 0 ]; then
    exit 1
fi

echo ""
echo "All tests passed!"
