#!/bin/bash
# Test script to compare patron_check_in endpoints between web.py and FastAPI

set -e

BASE_WEB="http://localhost:8080"
BASE_FASTAPI="http://localhost:18080"
USERNAME="openlibrary@example.com"
PASSWORD="admin123"

echo "=== Patron Check-In Comparison Test ==="

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
# DELETE ENDPOINT TESTS
#######################################

echo ""
echo "===== DELETE ENDPOINT TESTS ====="

# Test 1: DELETE unauthenticated (401)
echo ""
echo "=== Test 1: DELETE unauthenticated (401) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -X DELETE "$BASE_WEB/check-ins/1" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -X DELETE "$BASE_FASTAPI/check-ins/1" -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 2: DELETE non-existent check-in (404)
echo ""
echo "=== Test 2: DELETE non-existent (404) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X DELETE "$BASE_WEB/check-ins/99999999" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X DELETE "$BASE_FASTAPI/check-ins/99999999" -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 3: DELETE another user's check-in (403)
echo ""
echo "=== Test 3: DELETE another user's check-in (403) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X DELETE "$BASE_WEB/check-ins/4" -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X DELETE "$BASE_FASTAPI/check-ins/4" -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
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

# Test 4: POST create (200)
echo ""
echo "=== Test 4: POST create (200) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "month": 5, "day": 10}' -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/check-ins" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "month": 5, "day": 10}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 5: POST 400/422 invalid event_type
echo ""
echo "=== Test 5: POST 400/422 (invalid event_type) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 999, "year": 2025}' -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/check-ins" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 999, "year": 2025}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

# Accept both 400 (web.py) and 422 (FastAPI)
if [ "$WEB_CODE" = "$FASTAPI_CODE" ] || [ "$FASTAPI_CODE" = "422" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 6: POST 400/422 invalid date
echo ""
echo "=== Test 6: POST 400/422 (invalid date - day without month) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "day": 15}' -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/check-ins" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "day": 15}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

# Accept both 400 (web.py) and 422 (FastAPI)
if [ "$WEB_CODE" = "$FASTAPI_CODE" ] || [ "$FASTAPI_CODE" = "422" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 7: POST 401 unauthorized
echo ""
echo "=== Test 7: POST 401 (unauthorized) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025}' -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -X POST "$BASE_FASTAPI/works/OL45883W/check-ins" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 8: POST update (200)
echo ""
echo "=== Test 8: POST update (200) ==="
# Create an event first via web.py
CREATE_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025}')
EVENT_ID=$(echo "$CREATE_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

if [ -n "$EVENT_ID" ]; then
    echo "Created event ID: $EVENT_ID"
    echo "Web.py:"
    WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
        -H "Content-Type: application/json" \
        -d "{\"event_type\": 2, \"year\": 2025, \"event_id\": $EVENT_ID}" -w "\nStatus:%{http_code}")
    WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
    echo "Code: $WEB_CODE"

    # Create another for FastAPI
    CREATE_RESP2=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
        -H "Content-Type: application/json" \
        -d '{"event_type": 1, "year": 2025}')
    EVENT_ID2=$(echo "$CREATE_RESP2" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

    echo "FastAPI:"
    FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/check-ins" \
        -H "Content-Type: application/json" \
        -d "{\"event_type\": 2, \"year\": 2025, \"event_id\": $EVENT_ID2}" -w "\nStatus:%{http_code}")
    FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
    echo "Code: $FASTAPI_CODE"

    if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
        echo "PASS"
        ((PASSED++))
    else
        echo "FAIL"
        ((FAILED++))
    fi
else
    echo "SKIP: Could not create test event"
fi

# Test 9: POST 404 update non-existent
echo ""
echo "=== Test 9: POST 404 (update non-existent) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "event_id": 999999}' -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/check-ins" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "event_id": 999999}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 10: POST 403 update another user's event
echo ""
echo "=== Test 10: POST 403 (update another user's event) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_WEB/works/OL45883W/check-ins.json" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "event_id": 4}' -w "\nStatus:%{http_code}")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -b session=$SESSION -X POST "$BASE_FASTAPI/works/OL45883W/check-ins" \
    -H "Content-Type: application/json" \
    -d '{"event_type": 1, "year": 2025, "event_id": 4}' -w "\nStatus:%{http_code}")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
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

if [ $FAILED -gt 0 ]; then
    exit 1
fi

echo "All tests passed!"
