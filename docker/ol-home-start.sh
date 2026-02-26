#!/bin/bash

# quick method to start all ol services from one script
# inside an container, bypass all upstart/services

python --version

echo "Waiting for postgres..."
until pg_isready --host db; do sleep 5; done

echo "Waiting for Solr..."
until curl -s -o /dev/null -w "%{http_code}" "http://solr:8983/solr/openlibrary/select?q=*:*&rows=0&wt=json" | grep -q "200"; do
    sleep 5;
done
make reindex-solr
