#!/usr/bin/env bash

DUMP="$1"
DESTINATION="$2"

zcat "${DUMP}" | \
psql -d postgres --user=postgres -c  "COPY $DESTINATION FROM STDIN with delimiter E'\t' escape '\' quote E'\b' csv" &> logs/psql-chunk-ratings.txt
