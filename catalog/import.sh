#!/bin/bash

CONFIG=${1:?}
. $CONFIG

# # to destroy the database:
# rm $PHAROS_LOGFILE
# dropdb -U $PHAROS_DBUSER $PHAROS_DBNAME

# # to create a fresh database:
# createdb -U $PHAROS_DBUSER $PHAROS_DBNAME
# psql -U $PHAROS_DBUSER $PHAROS_DBNAME < $INFOGAMI_PATH/tdb/schema.sql

# identify the data to be imported
SOURCE_TYPE=${2:?}	# the record type; e.g., "marc"
SOURCE_ID=${3:?}	# the source catalog; e.g., "LC"
FILE_LOCATOR=${4:?}	# the file_locator (an Archive item id plus path to file); e.g., "marc_records_scriblio_net/part01.dat"

# note: the import program expects the data associated with FILE_LOCATOR on stdin

exec python2.4 $PHAROS_REPO/catalog/import.py $SOURCE_TYPE $SOURCE_ID $FILE_LOCATOR

