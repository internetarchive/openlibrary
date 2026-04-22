#! /bin/bash
# Note: The code in here is tested by scripts/monitoring/tests/test_utils_sh.py

olspy_find_worker() {
    # Note this is unused in this file, and is just a helper function
    local pattern="$1"

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
export -f olspy_find_worker

olspy_head() {
    local count="${COUNT:-5}"
    local only_other="${ONLY_OTHER:-false}"
    local exclude_internal="${EXCLUDE_INTERNAL:-false}"

    local process_pattern=""
    if [[ "$1" == "webpy" ]]; then
        process_pattern='openlibrary-server|coverstore-server'
    elif [[ "$1" == "fastapi" ]]; then
        process_pattern='uvicorn'
    elif [[ -z "$1" || "$1" == "--help" ]]; then
        echo "Usage: $0 <webpy|fastapi>"
        echo "Print the top stack frame(s) for each worker process using py-spy."
        echo ""
        echo "Arguments:"
        echo "  webpy    Inspect web.py worker processes (openlibrary-server, coverstore-server)"
        echo "  fastapi  Inspect FastAPI worker processes (uvicorn workers)"
        echo ""
        echo "Environment variables:"
        echo "  COUNT=<n>               Number of stack frames to print per worker (default: 5)"
        echo "  EXCLUDE_INTERNAL=true   Filter common library/internal frames before truncating"
        echo "  ONLY_OTHER=true         Skip workers whose first visible frame is classified"
        echo "                          as something other than 'other'"
        return 1
    else
        echo "Usage: $0 <webpy|fastapi>"
        echo "Unknown worker type: $1"
        return 1
    fi

    # Ss excludes the master process, and only gets the worker processes
    local pids=$(ps aux | grep -E "$process_pattern" | grep -v 'grep' | awk '$8 != "Ss"' | awk '{print $2}')

    for pid in $pids; do
        local dump=$(py-spy dump --nonblocking --pid $pid | tail -n +5)
        if [[ "$exclude_internal" == "true" ]]; then
            dump=$(echo "$dump" | exclude_internal_methods)
        fi

        dump=$(echo "$dump" | head -n $count)

        # Exclude if first line matches the exclude pattern
        if [[ "$only_other" == "true" && $(echo "$dump" | head -n1 | classify_workers_cur_fn | grep -vE '^other\.other$') ]]; then
            continue
        fi

        if [[ ${count} -ne 1 ]]; then
            echo "==> PID $pid <=="
        fi
        echo "$dump"
        if [[ ${count} -ne 1 ]]; then
            echo ""
        fi
    done 2>/dev/null
}
export -f olspy_head

exclude_internal_methods() {
    grep -vE 'ssl\.py|urllib3|httpcore|httpx/|http/client\.py|sentry_sdk|requests/|urllib/|wait \(threading.py|result \(concurrent/futures|async_utils\.py|socket\.py|_call_with_frames_removed|get_solr_keys|storify \(web\/utils.py|_write_raw \(gzip\.py|\(json\/|urlopen_keep_trying|PIL\/|importlib._bootstrap_external|_db_cursor'
}
export -f exclude_internal_methods

classify_workers_cur_fn() {
    awk '{
        if ($1 == "connect") print "db.connect";
        else if ($1 == "_db_execute") print "db._db_execute";
        else if ($1 == "commit") print "db.commit";
        else if ($1 == "query") print "db.query";
        else if ($2 ~ /web\/db\.py/) print "db.other";
        else if ($1 == "sleep") print "gunicorn.sleep";
        else if ($1 == "wait") print "gunicorn.wait";
        else if ($1 == "getaddrinfo") print "dns.getaddrinfo";
        else if ($1 == "get_availability") print "ia.get_availability";
        else if ($1 == "get_api_response") print "ia.get_api_response";
        else if ($1 == "s3_loan_api") print "ia.s3_loan_api";
        else if ($1 == "get_from_archive_bulk") print "ia.get_from_archive_bulk";
        else if ($1 == "get_groundtruth_availability") print "ia.get_groundtruth_availability";
        else if ($1 == "ia_username_exists") print "ia.username_exists";
        else if ($1 == "is_loaned_out_on_ia") print "ia.is_loaned_out_on_ia";
        else if ($1 == "xauth") print "ia.xauth";
        else if ($1 == "_solr_data") print "solr._solr_data";
        else if ($1 == "run_solr_query") print "solr.run_solr_query";
        else if ($2 ~ /web\/template.py/) print "webpy.template";
        else if ($1 == "__template__") print "webpy.template";
        else if ($0 ~ / _post \(openlibrary\/core\/lending\.py/) print "ia.lending_api_post";
        else if ($0 ~ / run \(asyncio\/runners\.py/) print "uvicorn.run";
        else if ($0 ~ / readline \(memcache\.py/) print "memcache.readline";
        else if ($0 ~ / _recv_value \(memcache\.py/) print "memcache._recv_value";
        else if ($0 ~ /info \(openlibrary\/core\/models\.py/) print "covers.info";
        else if ($0 ~ /GET \(openlibrary\/plugins\/worksearch\/code\.py/) print "ol.worksearch_GET";
        else if ($0 ~ /GET \(openlibrary\/views\/showmarc\.py/) print "ol.showmarc_GET";
        else if ($1 == "render_list_preview_image") print "ol.render_list_preview_image";
        else if ($2 ~ /infogami\/infobase\//) print "infobase.other";
        else print "other.other";
    }'
}
export -f classify_workers_cur_fn

log_workers_cur_fn() {
    local src="$1"
    local bucket="$2"

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

    COUNT=1 EXCLUDE_INTERNAL=true olspy_head $src \
        | classify_workers_cur_fn \
        | sort \
        | uniq -c \
        | awk -v date=$(date +%s) -v bucket="$bucket" '{print bucket "." $2 " " $1 " " date}' \
        | tee >(nc -q0 graphite.us.archive.org 2003)
}
export -f log_workers_cur_fn
