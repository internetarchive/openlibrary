#!/bin/bash
set -e
set -o xtrace

cd /openlibrary

createuser --superuser openlibrary
createdb openlibrary
psql --quiet openlibrary < openlibrary/core/users.sql
psql --quiet openlibrary < openlibrary/core/schema.sql
createdb coverstore
psql --quiet coverstore < openlibrary/coverstore/schema.sql
psql --quiet -U openlibrary openlibrary < scripts/dev-instance/dev_db.pg_dump
