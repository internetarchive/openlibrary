#!/bin/bash

python --version
source docker/ol-install-missing-deps.sh
exec scripts/infobase-server "$INFOBASE_CONFIG" $INFOBASE_OPTS 7000
