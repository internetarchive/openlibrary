#!/bin/bash
# Parses the last X lines of the nginx access log and logs the counts of
# each HTTP status code to statsd

STATSD_BUCKET=$1
# Get top IP counts in the last 17500 requests
# (As of 2024-01-08, that's about how many requests we have a minute)
HTTP_STATUS_COUNTS=$(
    tail -n 17500 /var/log/nginx/access.log | \
    grep -oE '" [0-9]{3} ' | \
    sort | uniq -c | sort -rn
)
# Output like this:
#   60319 " 200
#   55926 " 302
#    9267 " 404
#    8957 " 403
#    7297 " 499
#    7075 " 500
#     640 " 429
#     338 " 303
#     100 " 304
#      81 " 400

# Iterate over, and log in grafana to bucket; eg `stats.ol-covers.http_status.http_{NUM}`
while IFS= read -r line; do
    count=$(echo $line | awk '{print $1}')
    status=$(echo $line | awk '{print $3}')
    graphite_event="$STATSD_BUCKET.http_$status $count $(date +%s)"
    echo $graphite_event
    echo $graphite_event | nc -q0 graphite.us.archive.org 2003
done <<< "$HTTP_STATUS_COUNTS"
