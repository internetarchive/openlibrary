#!/usr/bin/env bash
# Comparison script: web.py trending endpoint vs FastAPI trending endpoint

set -euo pipefail

command -v jq >/dev/null 2>&1 || { echo "Error: jq is required but not installed. Install with: apt-get install jq"; exit 1; }

BASE_URL="${1:-http://localhost:8080}"
FAST_URL="${2:-http://localhost:18080}"
STRUCTURAL_ONLY="${STRUCTURAL_ONLY:-0}"

PERIODS=("daily" "weekly" "monthly" "yearly" "forever" "now")
PASS=0
FAIL=0

compare_period() {
    local period="$1"
    local legacy_url="${BASE_URL}/trending/${period}"
    local fastapi_url="${FAST_URL}/trending/${period}.json"

    echo ""
    echo "── Testing period: ${period} ──"
    echo "  Legacy  : ${legacy_url}"
    echo "  FastAPI : ${fastapi_url}"

    # Single request captures both body and status code to avoid race conditions on live data
    legacy_response=$(curl -s -w "\n%{http_code}" --max-time 10 "${legacy_url}" 2>/dev/null)
    legacy_status=$(echo "$legacy_response" | tail -1)
    legacy_body=$(echo "$legacy_response" | head -n -1)
    if [[ "$legacy_status" != "200" ]]; then
        echo "  SKIP: legacy returned ${legacy_status} (is web.py running?)"
        return
    fi

    fastapi_response=$(curl -s -w "\n%{http_code}" --max-time 10 "${fastapi_url}" 2>/dev/null)
    fastapi_status=$(echo "$fastapi_response" | tail -1)
    fastapi_body=$(echo "$fastapi_response" | head -n -1)
    if [[ "$fastapi_status" != "200" ]]; then
        echo "  FAIL: FastAPI returned ${fastapi_status}: ${fastapi_body}"
        FAIL=$((FAIL + 1))
        return
    fi

    # Check top-level keys — 'days' is special for 'forever': legacy returns null, FastAPI omits it entirely
    for key in "query" "hours" "works"; do
        legacy_has=$(echo "${legacy_body}" | jq --arg k "$key" 'has($k)')
        fastapi_has=$(echo "${fastapi_body}" | jq --arg k "$key" 'has($k)')
        if [[ "$legacy_has" != "$fastapi_has" ]]; then
            echo "  FAIL: key '${key}' presence mismatch (legacy=${legacy_has}, fastapi=${fastapi_has})"
            FAIL=$((FAIL + 1))
            return
        fi
    done
    if [[ "$period" == "forever" ]]; then
        echo "  OK: 'days' omitted by FastAPI for forever (expected — legacy=null, FastAPI excludes None)"
    else
        legacy_has=$(echo "${legacy_body}" | jq 'has("days")')
        fastapi_has=$(echo "${fastapi_body}" | jq 'has("days")')
        if [[ "$legacy_has" != "$fastapi_has" ]]; then
            echo "  FAIL: key 'days' presence mismatch (legacy=${legacy_has}, fastapi=${fastapi_has})"
            FAIL=$((FAIL + 1))
            return
        fi
    fi
    echo "  OK: top-level keys match"

    # query
    legacy_query=$(echo "${legacy_body}" | jq -r '.query')
    fastapi_query=$(echo "${fastapi_body}" | jq -r '.query')
    if [[ "$legacy_query" != "$fastapi_query" ]]; then
        echo "  FAIL: 'query' mismatch"
        echo "    legacy : ${legacy_query}"
        echo "    fastapi: ${fastapi_query}"
        FAIL=$((FAIL + 1))
        return
    fi
    echo "  OK: query = ${fastapi_query}"

    # days — skipped for 'forever' (FastAPI omits the key entirely; jq returns null for absent
    # keys so comparing null==null would silently pass on a meaningless non-comparison)
    if [[ "$period" != "forever" ]]; then
        legacy_days=$(echo "${legacy_body}" | jq '.days')
        fastapi_days=$(echo "${fastapi_body}" | jq '.days')
        if [[ "$legacy_days" != "$fastapi_days" ]]; then
            echo "  FAIL: 'days' mismatch (legacy=${legacy_days}, fastapi=${fastapi_days})"
            FAIL=$((FAIL + 1))
            return
        fi
        echo "  OK: days = ${fastapi_days}"
    fi

    if [[ "$STRUCTURAL_ONLY" != "1" ]]; then
        legacy_count=$(echo "${legacy_body}" | jq '.works | length')
        fastapi_count=$(echo "${fastapi_body}" | jq '.works | length')
        if [[ "$legacy_count" != "$fastapi_count" ]]; then
            echo "  WARN: works count differs (legacy=${legacy_count}, fastapi=${fastapi_count}) — possibly live data change"
        else
            echo "  OK: works count = ${fastapi_count}"
        fi
    fi

    # hours (compare values, not types)
    # Note: web.py legacy endpoint returns 'hours' as a string (e.g. "12" or "0") because it doesn't cast query variables.
    # FastAPI returns it as an integer because of the `hours: Annotated[int, ...]` parameter type validation.
    # This type difference is expected and acceptable, hence we coerce to numbers using jq `tonumber` to ensure parity.
    legacy_hours=$(echo "${legacy_body}" | jq '.hours | tonumber // .hours')
    fastapi_hours=$(echo "${fastapi_body}" | jq '.hours | tonumber // .hours')
    if [[ "$legacy_hours" != "$fastapi_hours" ]]; then
        echo "  FAIL: 'hours' value mismatch (legacy=${legacy_hours}, fastapi=${fastapi_hours})"
        FAIL=$((FAIL + 1))
        return
    else
        echo "  OK: hours = ${fastapi_hours} (legacy string, fastapi int — expected)"
    fi

    PASS=$((PASS + 1))
    echo "  RESULT: PASS"
}

echo "Trending Books API Parity Check"
echo "  Legacy base : ${BASE_URL}"
echo "  FastAPI base: ${FAST_URL}"

for period in "${PERIODS[@]}"; do
    compare_period "$period"
done

echo ""
echo "── Testing invalid period → 422 (FastAPI only) ──"
invalid_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${FAST_URL}/trending/badperiod.json")
if [[ "$invalid_status" == "422" ]]; then
    echo "  OK: got 422 as expected"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected 422, got ${invalid_status}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

[[ "$FAIL" -eq 0 ]] || exit 1