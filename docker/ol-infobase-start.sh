#!/bin/bash

python --version
exec scripts/infobase-server "$INFOBASE_CONFIG" $INFOBASE_OPTS 7000
