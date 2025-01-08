#!/usr/bin/env bash

# Creates reading log data, star ratings, community review tags, and a list
# for the openlibrary dev account.
#
# Run the following command:
# ./scripts/dev-instance/load-patron-data.sh

docker compose exec -T db psql --quiet -U openlibrary openlibrary < scripts/dev-instance/patron_data.sql

docker compose restart memcached
