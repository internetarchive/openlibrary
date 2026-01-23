#!/bin/bash

crontab /etc/cron.d/openlibrary.ol_home0
# 2026 Baseline Metrics - Run daily at 2 AM
echo "0 2 * * * cd /openlibrary && PYTHONPATH=. python scripts/2026_baseline_metrics.py >> /var/log/openlibrary/cron.log 2>&1" | crontab -
cron -f -L2
