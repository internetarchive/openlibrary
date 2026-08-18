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

(
    echo "Waiting for web container..."
    until curl -sf -o /dev/null http://web:8080/; do
        sleep 1
    done

    echo "Seeding /languages/* records from openlibrary.org..."
    python scripts/copydocs.py "/languages/*" --dest http://web:8080 \
        || echo "Warning: failed to seed /languages/* from openlibrary.org (offline?) - continuing."
) &
seed_languages_pid=$!

make reindex-solr

wait "$seed_languages_pid"
