#!/usr/bin/env bash
set -o xtrace  # Display each line before running it

DUMP="$1"
INSTANCES=$2


DUMP_SIZE=`time zcat ${DUMP} | wc -l`  # 6min (10 May 2019, OJF) ; 6min (Feb 2019, OJF)
echo $DUMP_SIZE  # 52730866 (10 May 2019) ; 51186504 (Feb 2019)
CHUNK_SIZE=`python3 -c "import math; print(math.ceil($DUMP_SIZE / $INSTANCES))"`
OFFSETS=`python3 -c "print(' '.join(map(str, range(0, $DUMP_SIZE, $CHUNK_SIZE))))"`
for offset in $OFFSETS; do
  docker-compose exec -d db ./psql-import-chunk.sh "${DUMP}" $offset $CHUNK_SIZE;
  sleep 180; # sleep to let it seek the dump in peace for a bit
done;
