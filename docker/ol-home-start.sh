#!/bin/bash

# quick method to start all ol services from one script
# inside an container, bypass all upstart/services

python --version

echo "Waiting for postgres..."
until pg_isready --host db; do sleep 5; done

# DEV ONLY: Auto-detect and fix Solr index issues
if [ "$LOCAL_DEV" = "true" ]; then
    echo "Running dev mode Solr health check..."

    # Wait for Solr to be ready
    until curl -s "http://solr:8983/solr/openlibrary/admin/ping" > /dev/null 2>&1; do
        echo "Waiting for Solr..."
        sleep 5
    done

    # Get DB and Solr counts
    DB_COUNT=$(psql --host db openlibrary -t -c "select count(*) from thing" | tr -d ' ')
    SOLR_COUNT=$(curl -s "http://solr:8983/solr/openlibrary/select?q=*:*&rows=0" | grep -oP '"numFound":\K\d+' || echo "0")

    echo "Solr health check: DB=$DB_COUNT records, Solr=$SOLR_COUNT indexed"

    if [ "$DB_COUNT" -gt 0 ] && [ "$SOLR_COUNT" -eq 0 ]; then
        echo "WARNING: DB has $DB_COUNT records but Solr has 0."
        echo "This usually means Solr schema has been updated but Solr hasn't reloaded."
        echo ""
        echo "To fix, run on your host machine:"
        echo "  docker-compose restart solr"
        echo ""
        echo "Then re-run indexing:"
        docker/solr-rebuild.sh
    else
        echo "Solr index OK, skipping reindex"
    fi
else
    make reindex-solr
fi
