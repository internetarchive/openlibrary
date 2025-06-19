#!/bin/bash

# quick method to start all ol services from one script
# inside an container, bypass all upstart/services

python --version

echo "Waiting for postgres..."
exec until pg_isready --host db; do sleep 5; done
make reindex-solr
