#!/bin/bash

# Test script for FastAPI authentication

echo "=== Testing FastAPI Authentication ==="
echo ""

# 1. Health check
echo "1. Testing health endpoint..."
curl -s --max-time 2 http://localhost:18080/health
echo ""
echo ""

# 2. Test auth endpoint without cookie
echo "2. Testing /account/test.json WITHOUT cookie..."
curl -s --max-time 2 http://localhost:18080/account/test.json | python3 -m json.tool 2>&1 | head -20
echo ""
echo ""

# 3. Login to get cookie
echo "3. Logging in to legacy app to get session cookie..."
curl -s --max-time 5 -X POST http://localhost:8080/account/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=openlibrary@example.com&password=admin123&remember=true" \
  -c /tmp/ol_test_cookies.txt >/dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "   Login successful, cookie saved"
else
    echo "   Login failed"
    exit 1
fi
echo ""

# 4. Test auth endpoint WITH cookie
echo "4. Testing /account/test.json WITH valid cookie..."
curl -s --max-time 2 http://localhost:18080/account/test.json \
  -b /tmp/ol_test_cookies.txt | python3 -m json.tool 2>&1 | head -30
echo ""
echo ""

# 5. Test protected endpoint with cookie
echo "5. Testing /account/protected.json WITH valid cookie..."
curl -s --max-time 2 http://localhost:18080/account/protected.json \
  -b /tmp/ol_test_cookies.txt | python3 -m json.tool 2>&1
echo ""
echo ""

# 6. Test protected endpoint without cookie
echo "6. Testing /account/protected.json WITHOUT cookie (should fail with 401)..."
curl -s --max-time 2 -w "\nHTTP Status: %{http_code}\n" http://localhost:18080/account/protected.json
echo ""

# 7. Test optional endpoint
echo "7. Testing /account/optional.json WITH cookie..."
curl -s --max-time 2 http://localhost:18080/account/optional.json \
  -b /tmp/ol_test_cookies.txt | python3 -m json.tool 2>&1
echo ""

echo "=== Tests Complete ==="
