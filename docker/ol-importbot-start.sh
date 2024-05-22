#!/bin/bash

python --version
PYTHONPATH=. scripts/manage-imports.py --config "$OL_CONFIG" import-all
