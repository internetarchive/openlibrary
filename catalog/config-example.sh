# path to the repository with the "catalog" code
export PHAROS_REPO="FIXME"

# path to the infogami code
export INFOGAMI_PATH="FIXME"

# how to connect to the database
export PHAROS_DBNAME=pharos
export PHAROS_DBUSER=pharos
export PHAROS_DBPASS=pharos
# export PHAROS_LOGFILE="/1/pharos/db/$PHAROS_DBNAME"

# what to call things in the database
export PHAROS_SITE="openlibrary.org"
export PHAROS_EDITION_PREFIX="b/"
export PHAROS_AUTHOR_PREFIX="a/"

# for the onix parser; any empty directory will do
export URL_CACHE_DIR=/1/pharos/sources/onix/urlcache/

export PYTHONPATH="$PHAROS_REPO:$INFOGAMI_PATH"

