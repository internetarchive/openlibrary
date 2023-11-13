#!/bin/bash

python --version
scripts/manage_imports.py --config "$OL_CONFIG" import-all
