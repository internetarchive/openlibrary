#!/bin/bash
# Solr rebuild script for local dev
# Usage: docker/solr-rebuild.sh
# Pre-condition: Assumes DB has data but Solr is empty (schema mismatch)

set -e

echo "Starting Solr migration..."

# Wait for Solr to be ready
until curl -s "http://solr:8983/solr/openlibrary/admin/ping" > /dev/null 2>&1; do
    echo "Waiting for Solr..."
    sleep 5
done

echo "Running reindex..."
make reindex-solr
