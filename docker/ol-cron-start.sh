#!/bin/bash

pip install s3cmd==2.4.0
crontab /etc/cron.d/openlibrary.ol_home0
cron -f -L2
