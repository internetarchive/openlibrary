#!/usr/bin/env bash
# Temporary comparison script — delete before merging.
# Tests lists_delete: POST /people/{username}/lists/{list_id}/delete.json

SESSION="${1:-}"

if [ -z "$SESSION" ]; then
  echo "Usage: $0 <session_cookie_value>"
  exit 1
fi

LIST_ID="${2:-OL6L}"
USERNAME="openlibrary"
ENDPOINT="/people/${USERNAME}/lists/${LIST_ID}/delete.json"

echo "Testing: POST ${ENDPOINT}"
echo ""

OLD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "http://localhost:8080${ENDPOINT}" \
  -H "Cookie: session=${SESSION}")

NEW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "http://localhost:18080${ENDPOINT}" \
  -H "Cookie: session=${SESSION}")

echo "web.py status:  $OLD_STATUS"
echo "FastAPI status: $NEW_STATUS"

# Unauthenticated test
OLD_UNAUTH=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "http://localhost:8080${ENDPOINT}")
NEW_UNAUTH=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "http://localhost:18080${ENDPOINT}")

echo ""
echo "Unauthenticated:"
echo "web.py:  $OLD_UNAUTH"
echo "FastAPI: $NEW_UNAUTH"
