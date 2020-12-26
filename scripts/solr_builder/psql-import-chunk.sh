#!/usr/bin/env bash

DUMP="$1"
OFFSET="$2"
COUNT="$3"

time zcat "${DUMP}" | \
tail -n +$((OFFSET+1)) | \
head -n $COUNT | \
sed --expression='s/\\u0000//g' | \
psql -d postgres --user=postgres -c  "COPY test FROM STDIN with delimiter E'\t' escape '\' quote E'\b' csv" &> logs/psql-chunk-$OFFSET.txt