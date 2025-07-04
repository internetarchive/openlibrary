# Note: The code in here is tested by scripts/monitoring/tests/test_utils_sh.py

py_spy_cur_fn() {
    pid=$1

    if [[ -z "$pid" || "$pid" == "--help" ]]; then
        echo "Usage: $0 <pid>"
        echo "Get the current function running on the PID process using py-spy"
        echo "Excludes some internal-y/system-y functions"
        return 1
    fi

    py-spy dump --nonblocking --pid $pid \
    | grep -vE '^(Process|Python|Thread)' \
    | grep -vE '(\bssl\.py|(readinto) .*socket\.py|http/client\.py|sentry_sdk|urllib3/connection\.py|<genexpr>|urllib3/connectionpool\.py|requests/(api|adapters|sessions)\.py)' \
    | head -n2 | tail -n1
}
export -f py_spy_cur_fn

py_spy_find_worker() {
    # Note this is unused in this file, and is just a helper function
    pattern="$1"

    if [[ -z "$pattern" || "$pattern" == "--help" ]]; then
        echo "Usage: $0 <pattern>"
        echo "Finds the first gunicorn worker process matching the pattern " \
             "anywhere in its stack trace using py-spy, and prints that stack trace"
        return 1
    fi

    for pid in $(ps aux | grep 'gunicorn' | grep -v 'grep' | awk '{print $2}'); do
        echo -n "$pid... "
        full_dump="$(py-spy dump --nonblocking --pid $pid)"
        match=$(echo "$full_dump" | grep -E "$pattern")
        if [ -z "$match" ]; then
            echo "✗"
        else
            echo "✓"
            echo "$full_dump"
            return 0
        fi
    done 2>/dev/null
    return 1
}
export -f py_spy_find_worker

log_workers_cur_fn() {
    BUCKET="$1"

    # Monitors the current function running on each gunicorn worker.
    #
    # Only explicitly names a few specific function to monitor:
    # - connect: psycopg2; this was a bottleneck before we switched to using direct
    #       IPs with psycopg2
    # - sleep|wait: Normal gunicorn behavior denoting a worker not doing anything
    # - getaddrinfo: Marker for DNS resolution time; saw this occasionally in Sentry's
    #       profiling for solr requests
    # - create_connection: Saw this in Sentry's profiling for IA requests; possibly
    #       related to requests connection pooling
    # - get_availability|get_api_response: Main time block for IA requests

    for pid in $(ps aux | grep -E 'openlibrary-server|coverstore-server' | grep -v 'grep' | awk '{print $2}'); do
        echo "$pid $(py_spy_cur_fn $pid)";
    done 2>/dev/null \
        | awk '{print $2}' \
        | awk '{if ($1 ~ /^(connect|sleep|wait|getaddrinfo|create_connection|get_availability|get_api_response)$/) print $1; else print "other"}' \
        | sort \
        | uniq -c \
        | awk -v date=$(date +%s) -v bucket="$BUCKET" '{print bucket "." $2 " " $1 " " date}' \
        | tee >(nc -q0 graphite.us.archive.org 2003)
}
export -f log_workers_cur_fn

log_recent_bot_traffic() {
    BUCKET="$1"
    CONTAINER_NAME="$2"

    # Get top IP counts in the last 17500 requests
    # (As of 2024-01-08, that's about how many requests we have a minute)
    BOT_TRAFFIC_COUNTS=$(
        docker exec -i "$CONTAINER_NAME" tail -n 17500 /var/log/nginx/access.log | \
        grep -oiE 'bingbot|claudebot|googlebot|applebot|gptbot|yandex.com/bots|ahrefsbot|amazonbot|petalbot|brightbot|SemanticScholarBot|uptimerobot|seznamebot|OAI-SearchBot|VsuSearchSpider' | \
        tr '[:upper:]' '[:lower:]' | \
        sed 's/[^[:alnum:]\n]/_/g' | \
        sort | uniq -c | sort -rn
    )

    # Output like this:
    # 1412516 bingbot
    #  513746 googlebot
    #  245256 ahrefsbot
    #  199586 gptbot
    #  140501 yandex_com_bots
    #   94740 amazonbot
    #   61533 applebot
    #   25958 petalbot
    #   17690 brightbot
    #    3436 semanticscholarbot
    #     894 uptimerobot

    # Iterate over, and log in grafana to bucket `stats.ol-covers.bot_traffic.http_{NUM}`
    while IFS= read -r line; do
        count=$(echo $line | awk '{print $1}')
        bot=$(echo $line | awk '{print $2}')
        graphite_event="$BUCKET.$bot $count $(date +%s)"
        echo $graphite_event
        echo $graphite_event | nc -q0 graphite.us.archive.org 2003
    done <<< "$BOT_TRAFFIC_COUNTS"

    # Also log other bots as a single metric
    OTHER_BOTS_COUNT=$(
        docker exec -i "$CONTAINER_NAME" tail -n 17500 /var/log/nginx/access.log | \
        grep -iE '\b[a-z_-]+(bot|spider|crawler)' | \
        grep -viE 'bingbot|claudebot|googlebot|applebot|gptbot|yandex.com/bots|ahrefsbot|amazonbot|petalbot|brightbot|SemanticScholarBot|uptimerobot|seznamebot|OAI-SearchBot|VsuSearchSpider' | \
        wc -l
    )

    graphite_event="$BUCKET.other $OTHER_BOTS_COUNT $(date +%s)"
    echo $graphite_event
    echo $graphite_event | nc -q0 graphite.us.archive.org 2003

    # And finally, also log non bot traffic
    NON_BOT_TRAFFIC_COUNT=$(
        docker exec -i "$CONTAINER_NAME" tail -n 17500 /var/log/nginx/access.log | \
        grep -viE '\b[a-z_-]+(bot|spider|crawler)' | \
        wc -l
    )

    graphite_event="$BUCKET.non_bot $NON_BOT_TRAFFIC_COUNT $(date +%s)"
    echo $graphite_event
    echo $graphite_event | nc -q0 graphite.us.archive.org 2003
}
export -f log_recent_bot_traffic

log_recent_http_statuses() {
    BUCKET="$1"
    CONTAINER_NAME="$2"

    # Get top IP counts in the last 17500 requests
    # (As of 2024-01-08, that's about how many requests we have a minute)
    HTTP_STATUS_COUNTS=$(
        docker exec -i "$CONTAINER_NAME" tail -n 17500 /var/log/nginx/access.log | \
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

    # Iterate over, and log in grafana to bucket `stats.ol-covers.http_status.http_{NUM}`
    while IFS= read -r line; do
        count=$(echo $line | awk '{print $1}')
        status=$(echo $line | awk '{print $3}')
        graphite_event="$BUCKET.http_$status $count $(date +%s)"
        echo $graphite_event
        echo $graphite_event | nc -q0 graphite.us.archive.org 2003
    done <<< "$HTTP_STATUS_COUNTS"
}
export -f log_recent_http_statuses

log_top_ip_counts() {
    BUCKET="$1"
    CONTAINER_NAME="$2"

    # Get top IP counts in the last 17500 requests
    # (As of 2024-01-08, that's about how many requests we have a minute)
    TOP_IP_COUNTS=$(
        docker exec -i "$CONTAINER_NAME" tail -n 17500 /var/log/nginx/access.log | \
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
        graphite_event="$BUCKET.ip_$(printf "%02d" $i) $count $(date +%s)"
        echo $graphite_event
        echo $graphite_event | nc -q0 graphite.us.archive.org 2003
        i=$((i+1))
    done
}
export -f log_top_ip_counts
