#!/bin/bash

python --version
python scripts/affiliate_server.py "$AFFILIATE_CONFIG" 0.0.0.0:31337
