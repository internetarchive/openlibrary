#!/bin/bash
# Test script to compare public_my_books_json endpoint between web.py and FastAPI

set -e

BASE_WEB="http://localhost:8080"
BASE_FASTAPI="http://localhost:18080"
USERNAME="openlibrary@example.com"
PASSWORD="admin123"

echo "=== public_my_books_json Comparison Test ==="

# Create a session
echo "Logging in..."
LOGIN_RESP=$(curl -s -c /tmp/cookies_mybooks.txt -b /tmp/cookies_mybooks.txt -X POST "$BASE_WEB/account/login" \
  -d "username=$USERNAME&password=$PASSWORD&remember=true" -w "\n%{http_code}" -L)

SESSION=$(grep session /tmp/cookies_mybooks.txt | awk '{print $7}')

if [ -z "$SESSION" ]; then
    echo "ERROR: Failed to get session cookie"
    exit 1
fi

echo "Session: ${SESSION:0:20}..."

PASSED=0
FAILED=0

#######################################
# Tests
#######################################

# Test 1: Valid user, want-to-read (unauthenticated - should be private)
echo ""
echo "=== Test 1: want-to-read (unauthenticated) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_WEB/people/openlibrary/books/want-to-read.json")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_FASTAPI/people/openlibrary/books/want-to-read.json")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 2: Valid user, currently-reading (unauthenticated)
echo ""
echo "=== Test 2: currently-reading (unauthenticated) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_WEB/people/openlibrary/books/currently-reading.json")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_FASTAPI/people/openlibrary/books/currently-reading.json")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 3: Valid user, already-read (unauthenticated)
echo ""
echo "=== Test 3: already-read (unauthenticated) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_WEB/people/openlibrary/books/already-read.json")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_FASTAPI/people/openlibrary/books/already-read.json")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 4: With pagination
echo ""
echo "=== Test 4: With pagination (page=2) ==="
echo "Web.py:"
WEB_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_WEB/people/openlibrary/books/want-to-read.json?page=2")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_FASTAPI/people/openlibrary/books/want-to-read.json?page=2")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 5: With limit
echo ""
echo "=== Test 5: With limit ==="
echo "Web.py:"
WEB_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_WEB/people/openlibrary/books/want-to-read.json?limit=10")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_FASTAPI/people/openlibrary/books/want-to-read.json?limit=10")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

if [ "$WEB_CODE" = "$FASTAPI_CODE" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 6: Invalid shelf key (FastAPI returns 422 for validation error)
echo ""
echo "=== Test 6: Invalid shelf key ==="
echo "Web.py:"
WEB_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_WEB/people/openlibrary/books/invalid-shelf.json")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_FASTAPI/people/openlibrary/books/invalid-shelf.json")
FASTAPI_CODE=$(echo "$FASTAPI_RESP" | grep Status | cut -d: -f2)
echo "Code: $FASTAPI_CODE"

# Accept both 404 (web.py) and 422 (FastAPI validation error)
if [ "$WEB_CODE" = "$FASTAPI_CODE" ] || [ "$FASTAPI_CODE" = "422" ]; then
    echo "PASS"
    ((PASSED++))
else
    echo "FAIL"
    ((FAILED++))
fi

# Test 7: Non-existent user
echo ""
echo "=== Test 7: Non-existent user ==="
echo "Web.py:"
WEB_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_WEB/people/nonexistentuser123/books/want-to-read.json")
WEB_CODE=$(echo "$WEB_RESP" | grep Status | cut -d: -f2)
echo "Code: $WEB_CODE"

echo "FastAPI:"
FASTAPI_RESP=$(curl -s -w "\nStatus:%{http_code}" "$BASE_FASTAPI/people/nonexistentuser123/books/want-to-read.json")
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
