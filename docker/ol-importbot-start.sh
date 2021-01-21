#!/bin/bash

python --version
scripts/manage-imports.py --config "$OL_CONFIG" $IMPORTBOT_OPTS import-all
