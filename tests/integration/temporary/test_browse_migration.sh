#!/usr/bin/env bash
# Test script to compare browse endpoints between web.py and FastAPI
# TODO: DELETE BEFORE MERGING, ONLY NEEDED FOR COMPARISON TESTING

set -euo pipefail

# Check for jq dependency
command -v jq >/dev/null 2>&1 || { echo "Error: jq is required. Install with: apt-get install jq"; exit 1; }

BASE_WEB="${1:-http://localhost:8080}"
BASE_FASTAPI="${2:-http://localhost:18080}"

echo "==============================================="
echo "   ENDPOINT TESTS   "
echo "==============================================="
echo "Legacy Base:  $BASE_WEB"
echo "FastAPI Base: $BASE_FASTAPI"

PASSED=0
FAILED=0

run_test() {
    local test_name="$1"
    local query_string="$2"

    echo -e "\n── $test_name ──"

    # Fetch Web.py
    WEB_RESP=$(curl -s "$BASE_WEB/browse.json$query_string" -w "\nStatus:%{http_code}")
    WEB_CODE=$(echo "$WEB_RESP" | tail -n 1 | cut -d: -f2)
    WEB_BODY=$(echo "$WEB_RESP" | sed '$d')

    # Fetch FastAPI
    FAST_RESP=$(curl -s "$BASE_FASTAPI/browse.json$query_string" -w "\nStatus:%{http_code}")
    FAST_CODE=$(echo "$FAST_RESP" | tail -n 1 | cut -d: -f2)
    FAST_BODY=$(echo "$FAST_RESP" | sed '$d')

    # Ensures 'query' and 'works' keys exist in both
    for key in "query" "works"; do
        if ! echo "$FAST_BODY" | jq -e "has(\"$key\")" > /dev/null; then
             echo "FAIL: FastAPI response missing key '$key'"
             FAILED=$((FAILED + 1))
             return 0
        fi
    done

    # 2. Body Parity Check
    WEB_NORM=$(echo "$WEB_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")
    FAST_NORM=$(echo "$FAST_BODY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),sort_keys=True))")

    if [ "$WEB_CODE" = "$FAST_CODE" ] && [ "$WEB_NORM" = "$FAST_NORM" ]; then
        echo "RESULT: PASS (Status: $WEB_CODE)"
        PASSED=$((PASSED + 1))
    else
        echo "RESULT: FAIL"
        echo "Codes: Web.py ($WEB_CODE) vs FastAPI ($FAST_CODE)"
        if [ "$WEB_NORM" != "$FAST_NORM" ]; then
            echo "Body Mismatch detected. Use 'diff' to compare outputs if necessary."
        fi
        FAILED=$((FAILED + 1))
    fi
}

# --- Tests ---

run_test "Test 1: Default parameters" ""
run_test "Test 2: Search query 'tolkien'" "?q=tolkien"
run_test "Test 3: Pagination (Limit 5, Page 2)" "?q=harry&limit=5&page=2"
run_test "Test 4: Subjects and sorting" "?subject=romance&sorts=new"
run_test "Test 5: Multiple sort keys" "?q=magic&sorts=new,title"

echo -e "\n── Test 6: Validation (Invalid limit) ──"
# In FastAPI returns 422, web.py returns 500
WEB_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_WEB/browse.json?limit=abc")
FAST_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_FASTAPI/browse.json?limit=abc")

if [ "$WEB_CODE" = "500" ] && [ "$FAST_CODE" = "422" ]; then
    echo "RESULT: PASS (Expected Legacy 500 vs FastAPI 422)"
    PASSED=$((PASSED + 1))
else
    echo "RESULT: FAIL (Got $WEB_CODE vs $FAST_CODE)"
    FAILED=$((FAILED + 1))
fi

# --- Final Summary ---
echo -e "\n==============================================="
echo "Summary: $PASSED Passed, $FAILED Failed"
echo "==============================================="

if [ $FAILED -gt 0 ]; then
    exit 1
fi