#!/bin/bash

python --version
scripts/infobase-server "$INFOBASE_OPTS" "$INFOBASE_CONFIG" fastcgi 7000
