#!/bin/bash

export PHAROS_DBNAME=crap
export PHAROS_DBUSER=pharos
export PHAROS_DBPASS=pharos
export PHAROS_LOGFILE="/1/pharos/db/$PHAROS_DBNAME"

export PHAROS_SITE="openlibrary.org"
export PHAROS_EDITION_PREFIX="b/"
export PHAROS_AUTHOR_PREFIX="a/"

export PHAROS_SOURCE_DIR=/1/pharos/sources/
export URL_CACHE_DIR=/1/pharos/sources/onix/urlcache/
export PHAROS_REPO=~dbg/repo

# destroy the database
# rm $PHAROS_LOGFILE
# dropdb -U $PHAROS_DBUSER $PHAROS_DBNAME

# create a fresh database
# createdb -U $PHAROS_DBUSER $PHAROS_DBNAME
# psql -U $PHAROS_DBUSER $PHAROS_DBNAME < $PHAROS_REPO/infogami/infogami/tdb/schema.sql

# maybe need this ...
# export PYTHONPATH=/home/dbg/lib/python

# import some data
SOURCE_TYPE=${1:?}
SOURCE_NAME=${2:?}
SOURCE_POS=$3

python2.4 import.py $SOURCE_TYPE $SOURCE_NAME $SOURCE_POS
