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

    # Bots that aren't in obfi_grep_bots' list are handled by monitor.py, which
    # promotes the high-volume ones to their own series and sums the rest into
    # `$BUCKET.other`. See list_unknown_bot_counts below.

    # And finally, also log non bot traffic. Scoped to the User-Agent field, to
    # match list_unknown_bot_counts: excluding on the whole line here while the
    # bot path matches only the UA would leave a browser request for /robots.txt
    # counted in neither, so the two would stop adding up to the total.
    NON_BOT_TRAFFIC_COUNT=$(
        obfi_in_docker obfi_previous_minute | \
        awk -F'"' '{print $6}' | \
        grep -viE '\b[a-z_-]+(bot|spider|crawler)' | \
        obfi_grep_bots -v | \
        wc -l
    )

    graphite_event="$BUCKET.non_bot $NON_BOT_TRAFFIC_COUNT $(date +%s)"
    echo $graphite_event
    echo $graphite_event | nc -q0 graphite.us.archive.org 2003
}
export -f log_recent_bot_traffic

list_unknown_bot_counts() {
    # Per-agent counts for traffic that self-identifies as a bot but is not in
    # obfi_grep_bots' hardcoded list. Prints to stdout rather than submitting to
    # graphite: monitor.py decides which of these names are high-volume enough
    # to get their own series, and sums the remainder into `other`.

    # Only look at the User-Agent (the 6th "-delimited field), not the whole log
    # line. Matching the whole line invents agents out of ordinary traffic: a
    # request for /robots.txt becomes "robot", /works/OL1W/I-Robot becomes
    # "i_robot", and any visitor could name a metric by requesting a URL.

    # Take only the FIRST match in each UA, unlike obfi_top_bots. Polite crawlers
    # name themselves a second time in a self-documenting URL -- eg
    # "OAI-SearchBot/1.0; +https://openai.com/searchbot" -- and counting every
    # match gives that one agent two series ("oai_searchbot" and a phantom
    # "searchbot"), doubles its volume, and spends two promotion slots on it.

    # Separators become "-" first so obfi_grep_bots, whose patterns contain
    # literal hyphens, also rejects a UA that spells a known bot with
    # underscores ("Aranet_SearchBot") and would otherwise mint -- and overwrite
    # -- that bot's real series. Then "-" becomes "_" for the metric path.
    obfi_in_docker obfi_previous_minute | \
        awk -F'"' '{print $6}' | \
        tr '[:upper:]' '[:lower:]' | \
        obfi_grep_bots -v | \
        awk 'match($0, /[a-z_-]+(bot|spider|crawler)/) { print substr($0, RSTART, RLENGTH) }' | \
        sed 's/[^[:alnum:]\n]/-/g' | \
        obfi_grep_bots -v | \
        sed 's/-/_/g' | \
        sort | uniq -c | sort -rn

    # Output like this:
    #     412 semrushbot
    #     118 dataforseobot
    #       3 somerandomcrawler
}
export -f list_unknown_bot_counts

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

log_top_response_times() {
    BUCKET="$1"

    # Get top response times in the last minute
    TOP_RESPONSE_TIMES=$(
        obfi_in_docker obfi_previous_minute | \
        obfi_top_response_times | \
        tail -n +2
    )
    # Output like this from obfi_top_response_times:
    # n=26383  min=0.000s  avg=0.386s  max=53.666s
    #      5694 10ms
    #      4273 100ms
    #     14669 1000ms
    #      1491 5000ms
    #       225 10000ms
    #        19 20000ms
    #        12 LONG

    local ts=$(date +%s)
    # Iterate over, and log in grafana to bucket eg `stats.ol-covers.response_times.10000ms`
    while IFS= read -r line; do
        count=$(echo $line | awk '{print $1}')
        time_bucket=$(echo $line | awk '{print $2}')
        graphite_event="$BUCKET.$time_bucket $count $ts"
        echo $graphite_event
        echo $graphite_event | nc -q0 graphite.us.archive.org 2003
    done <<< "$TOP_RESPONSE_TIMES"
}
