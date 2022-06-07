#!/usr/bin/env bash

# Creates database backup SQL script file.
#
# This script generates `dev_db.pg_dump` when the following commands are executed:
#
# docker-compose exec db bash
# ./openlibrary/scripts/dev-instance/create-dev-db-pgdump.sh > openlibrary/scripts/dev-instance/dev_db.pg_dump

OL_USER=openlibrary

pg_dump --host=db -U $OL_USER openlibrary
