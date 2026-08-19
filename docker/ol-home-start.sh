#!/bin/bash

source docker/ol-install-missing-deps.sh

# Clone or update docs wiki so developers and AI assistants can search
# documentation locally without switching to the browser.
if [ -d "/openlibrary/docs/wiki/.git" ]; then
    echo "Updating docs wiki..."
    cd /openlibrary/docs/wiki && git pull --ff-only
else
    echo "Cloning docs wiki..."
    git clone https://github.com/internetarchive/openlibrary.wiki.git /openlibrary/docs/wiki
fi
cd /openlibrary

# Latest last_modified among /type/language docs on the given OL instance, or empty if unknown.
latest_language_timestamp() {
    curl -sf "$1/query.json?type=/type/language&sort=-last_modified&limit=1&last_modified=" \
        | python -c "import json, sys; d = json.load(sys.stdin); print(d[0]['last_modified']['value'] if d else '')" 2>/dev/null
}

seed_languages() {
    echo "Waiting for web container..."
    local wait_timeout=60
    local waited=0
    until curl -sf -o /dev/null http://web:8080/; do
        if [ "$waited" -ge "$wait_timeout" ]; then
            echo "Warning: web container not reachable after ${wait_timeout}s - skipping /languages/* seed."
            return
        fi
        waited=$((waited + 1))
        sleep 1
    done

    local_ts=$(latest_language_timestamp http://web:8080)
    remote_ts=$(latest_language_timestamp https://openlibrary.org)

    if [ -n "$local_ts" ] && [ -n "$remote_ts" ] && [[ ! "$local_ts" < "$remote_ts" ]]; then
        echo "Local /languages/* already up to date with openlibrary.org - skipping seed."
        return
    fi

    echo "Seeding /languages/* records from openlibrary.org..."
    python scripts/copydocs.py "/languages/*" --dest http://web:8080 \
        || echo "Warning: failed to seed /languages/* from openlibrary.org (offline?) - continuing."
}

seed_languages &
seed_languages_pid=$!

make reindex-solr

wait "$seed_languages_pid"
