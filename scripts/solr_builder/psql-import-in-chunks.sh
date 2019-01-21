#!/usr/bin/env bash

DUMP="$1"
INSTANCES=$2


DUMP_SIZE=`time zcat ${DUMP} | wc -l` # ~7m
echo $DUMP_SIZE # 50997224
CHUNK_SIZE=`python3 -c "import math; print(math.ceil($DUMP_SIZE / $INSTANCES))"`
OFFSETS=`python3 -c "print(' '.join(map(str, range(0, $DUMP_SIZE, $CHUNK_SIZE))))"`
for offset in $OFFSETS; do
  echo docker-compose exec db ./psql-import-chunk.sh "${DUMP}" $offset $CHUNK_SIZE | tee /dev/tty | bash;
  echo sleep 180 | tee /dev/tty | bash; # sleep to let it seek the dump in peace for a bit
done;