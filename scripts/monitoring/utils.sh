log_workers_cur_fn() {
    BUCKET="$1"
    for pid in $(ps aux | grep 'gunicorn' | grep -v 'grep' | awk '{print $2}'); do
        echo "$pid $(py-spy dump --nonblocking --pid $pid | head -n5 | tail -n1 | grep -oE '\S+' | head -n1)";
    done 2>/dev/null \
        | awk '{print $2}' \
        | awk '{if ($1 ~ /^(connect|sleep|wait)$/) print $1; else print "other"}' \
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