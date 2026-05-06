# Note: The code in here is tested by scripts/monitoring/tests/test_utils_sh.py

log_recent_bot_traffic() {
    BUCKET="$1"

    # Get top bot user agent counts in the last minute
    BOT_TRAFFIC_COUNTS=$(obfi_in_docker obfi_previous_minute | obfi_top_bots)

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
        obfi_in_docker obfi_previous_minute | \
        grep -iE '\b[a-z_-]+(bot|spider|crawler)' | \
        obfi_grep_bots -v | \
        wc -l
    )

    graphite_event="$BUCKET.other $OTHER_BOTS_COUNT $(date +%s)"
    echo $graphite_event
    echo $graphite_event | nc -q0 graphite.us.archive.org 2003

    # And finally, also log non bot traffic
    NON_BOT_TRAFFIC_COUNT=$(
        obfi_in_docker obfi_previous_minute | \
        grep -viE '\b[a-z_-]+(bot|spider|crawler)' | \
        obfi_grep_bots -v | \
        wc -l
    )

    graphite_event="$BUCKET.non_bot $NON_BOT_TRAFFIC_COUNT $(date +%s)"
    echo $graphite_event
    echo $graphite_event | nc -q0 graphite.us.archive.org 2003
}
export -f log_recent_bot_traffic

log_recent_http_statuses() {
    BUCKET="$1"

    # Get top http counts from previous minute
    HTTP_STATUS_COUNTS=$(obfi_in_docker obfi_previous_minute | obfi_top_http_statuses)
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

    # Get top IP counts in the last minute
    TOP_IP_COUNTS=$(
        obfi_in_docker obfi_previous_minute | \
        obfi_top_ips 25 | \
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
