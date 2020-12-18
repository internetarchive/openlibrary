#!/bin/bash

python --version
python scripts/affiliate-server "$AFFILIATE_CONFIG" 0.0.0.0:31337
