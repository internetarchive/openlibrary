#!/bin/bash

echo "Starting monitoring on $HOSTNAME"

PYTHONPATH=. python scripts/monitoring/monitor.py
