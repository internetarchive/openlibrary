#!/usr/bin/env bash

DUMP="$1"
DESTINATION="$2"

time zcat "${DUMP}" | \
sed --expression='s/\\u0000//g' | \
psql -d postgres --user=postgres -c  "
    TRUNCATE $DESTINATION;
    COPY $DESTINATION
    FROM STDIN with delimiter E'\t' escape '\' quote E'\b' FREEZE csv
"
