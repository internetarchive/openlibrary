set -x

CONTAINER=db
DATE="2019-08-31"
FILE="https://archive.org/download/ol_dump_$DATE/ol_dump_$DATE.txt.gz"

alias psql='docker-compose exec -T -u postgres $CONTAINER psql postgres -X -t -A $1'

# Make sure our container is running
docker-compose up -d --no-deps $CONTAINER
sleep 20 # let it initialize

# create table
time docker-compose exec -u postgres $CONTAINER psql -d postgres -f sql/create-dump-table.sql

# Download dump and load into database
# TODO - Verify that # of lines, DB Copy record count, and Select count(*) counts all match
time docker-compose exec -u postgres $CONTAINER bash -c "time curl -L ${FILE} | gunzip | sed --expression='s/\\\\u0000//g' |  psql -d postgres --user=postgres -c \"COPY entity FROM STDIN with delimiter E'\t' escape '\' quote E'\b' csv\" "

# Create indexes and procedures, then VACUUM ANALYZE
time docker-compose exec -u postgres $CONTAINER psql -d postgres -f sql/create-indices.sql

