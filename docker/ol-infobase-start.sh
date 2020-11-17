#!/bin/bash

python --version
scripts/infobase-server "$INFOBASE_CONFIG" $INFOBASE_OPTS 7000
