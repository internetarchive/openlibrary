#!/usr/bin/env bash

DUMP="$1"
OFFSET="$2"
COUNT="$3"

if [ -z $OFFSET ] && [ -z $COUNT ]
then
  time zcat "${DUMP}" | \
  sed --expression='s/\\u0000//g' | \
  psql -d postgres --user=postgres -c  "COPY entity FROM STDIN with delimiter E'\t' escape '\' quote E'\b' csv"
else
  time zcat "${DUMP}" | \
  tail -n +$((OFFSET+1)) | \
  head -n $COUNT | \
  sed --expression='s/\\u0000//g' | \
  psql -d postgres --user=postgres -c  "COPY entity FROM STDIN with delimiter E'\t' escape '\' quote E'\b' csv" &> logs/psql-chunk-$OFFSET.txt
fi