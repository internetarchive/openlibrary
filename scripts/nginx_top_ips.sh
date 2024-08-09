#!/bin/bash
# Parses the last X lines of the nginx access log and logs the counts of
# the top 25 IP addresses to statsd

STATSD_BUCKET=$1
# Get top IP counts in the last 17500 requests
# (As of 2024-01-08, that's about how many requests we have a minute)
TOP_IP_COUNTS=$(
    tail -n 17500 /var/log/nginx/access.log | \
    grep -oE '^[^ ]+' | \
    sort | uniq -c | sort -rn | \
    head -n 25 | \
    awk '{print $1}'
)
# Output like this before the last awk:
#  182089 0.125.240.191
#  181874 0.36.168.144
#  181779 0.198.202.145
#  181093 0.233.200.251

# Iterate over, and log in grafana to bucket `ol.stats.top_ip_1`, `ol.stats.top_ip_2`, etc.
i=1
for count in $TOP_IP_COUNTS; do
    graphite_event="$STATSD_BUCKET.ip_$(printf "%02d" $i) $count $(date +%s)"
    echo $graphite_event
    echo $graphite_event | nc -q0 graphite.us.archive.org 2003
    i=$((i+1))
done
