#! /bin/bash
# Set of utility scripts for working with nginx logs in Open Library.
#
# To use: `source scripts/obfi.sh`
# Be sure to add SEED_PATH to your .bashrc or .bash_profile, eg:
# export SEED_PATH=PATH

obfi() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        echo "Usage: obfi [cmd] [file]"
        echo "The start of the nginx log utility scripts."
        echo "If no command is provided, defaults to 'tail -f'."
        echo "If no file is provided, finds the nginx container and uses its access log."
        echo ""
        echo "Source obfi commands:"
        echo "  obfi | ...                            - follows the live logs"
        echo "  obfi 'tail -f' | ...                  - the default command (same as above)"
        echo "  obfi 'tac' | ...                      - reads the logs in reverse"
        echo "  obfi_previous_minute | ...            - reads the logs from the previous minute"
        echo "  obfi_previous_hour | ...              - reads the logs from the previous hour"
        echo "  obfi_walk_logs <days> | ...           - walks the gzip logs for the last <days> days"
        echo "  obfi_range <start> <end> | ...        - ALPHA: reads the logs from the given range."
        echo "                                          Only works for today's logs (access.log). Expects"
        echo "                                          timestamps in milliseconds, eg from Grafana URLs."
        echo ""
        echo "From here, you can filter the logs with grep as normal, or the obfi grep commands."
        echo "These commands use grep, so support grep options like -i, -v, etc. See grep --help."
        echo ""
        echo "Grep commands:"
        echo "  obfi | grep "pattern..." | ...        - grep the logs for a pattern normally"
        echo "  obfi | obfi_grep_bots | ...           - requests from known bots"
        echo "  obfi | obfi_grep_bots -v | ...        - requests NOT from known bots"
        echo "  obfi | obfi_grep_secondary_reqs | ... - eg /static, /images, etc"
        echo ""
        echo "Once you've filtered to the logs you want, you can reduce them with the obfi aggregation commands."
        echo ""
        echo "Aggregation commands:"
        echo "  obfi tac | obfi_count_minute | ...    - count the logs by minute"
        echo "  obfi tac | obfi_count_hour | ...      - count the logs by hour"
        echo "  obfi_walk_logs | obfi_count_day | ... - count the logs by day"
        echo "  obfi_previous_minute | obfi_top_ips   - count and sort the top IPs"
        echo ""
        echo "For dealing with spam, you can decode obfuscated IPs with the obfi commands."
        echo "First, start listening with obfi_listen, then decode IPs with obfi_decode."
        echo ""
        echo "NOTE: SEED_PATH must be set to the path to seed.txt; add it to your ~/.bashrc"
        echo "Obfuscation commands:"
        echo "  obfi_listen                           - listens in the background for 1min"
        echo "  obfi_stop_listening                   - stops listening for obfuscated IPs"
        echo "  obfi_decode <ip>                      - decodes the obfuscated IP address <ip>"
        echo "  ... | obfi_top_ips | obfi_decode_all  - decodes all obfuscated IPs in stdin"
        echo ""
        echo "Configuration variables:"
        echo "  SEED_PATH=""                          - path to seed.txt, used for decoding IPs"
        echo "  OBFI_LOG_DIR="/1/var/log/nginx"       - path to the nginx log directory. For "
        echo "                                          containers, defaults to /var/log/nginx."
        echo ""
        return 0
    fi
    CMD=${1:-"tail -f"}


    if [  -z "$CONTAINER" ]; then
        CONTAINER=$(docker ps --format '{{.Names}}' | grep nginx)
    fi

    if [ ! -z "$CONTAINER" ]; then
        LOG_DIR="${OBFI_LOG_DIR:-/var/log/nginx}"
        FILE=${2:-"$LOG_DIR/access.log"}
        echo "Reading from $FILE in $CONTAINER" 1>&2
        docker exec -i "$CONTAINER" $CMD "$FILE"
    else
        LOG_DIR="${OBFI_LOG_DIR:-/1/var/log/nginx}"
        FILE=${2:-"$LOG_DIR/access.log"}
        echo "Reading from $FILE" 1>&2
        sudo -E $CMD $FILE
    fi
}

###############################################################
# Source commands
###############################################################

obfi_walk_logs() {
    if [[ -z "$1" || "$1" == "-h" || "$1" == "--help" ]]; then
        echo "Usage: obfi_walk_logs <days>"
        echo "Walks the gzip logs for the last <days> days, catting their outputs together."
        return 1
    fi

    LOG_DIR="${OBFI_LOG_DIR:-/1/var/log/nginx}"

    COUNT=$1
    for file in $(ls -tr $LOG_DIR/access.log-*.gz | tail -n $COUNT); do
        echo $file 1>&2
        sudo zcat $file
    done
    echo "$LOG_DIR/access.log" 1>&2
    sudo cat "$LOG_DIR/access.log"
}

obfi_previous_minute() {
    # Iterate over the logs and print the logs from the previous minute
    # E.g. running the script at 11:20:36 will print logs from 11:19:00 to 11:19:59
    CUR_MIN=$(date +"%Y-%m-%d %H:%M:00")
    CUR_MIN=$(date -d "$CUR_MIN" +%s)
    PREV_MIN_START=$(($CUR_MIN - 60))

    obfi_range $(($PREV_MIN_START * 1000)) $(($CUR_MIN * 1000 - 1))
}

obfi_previous_hour() {
    # Iterate over the logs and print the logs from the previous hour
    # e.g. running the script at 11:20:36 will print logs from 10:00 to 10:59

    # Need to zero out the minutes and seconds
    NOW=$(date +"%Y-%m-%d %H:00:00")
    NOW=$(date -d "$NOW" +%s)
    HOUR_START=$(($NOW - 3600))
    HOUR_END=$(($NOW - 1))

    obfi_range $(($HOUR_START * 1000)) $(($HOUR_END * 1000))
}

obfi_range() {
    # Iterate over the logs and print the logs from the given range
    if [[ -z "$1" || -z "$2" ]]; then
        echo "Usage: obfi_range <start> <end>"
        echo "Example: obfi_range 1748502382753 1748503464280"
        echo "Example: obfi_range $(($(date +%s) * 1000 - 3600000)) END"
        echo "Timestamps eg from grafana URLs"
        return 1
    fi

    START=$1
    END=$2

    START_FILE=$(obfi_find_log $START)
    if [[ $? -ne 0 ]]; then
        echo "Error: Could not find log file for start timestamp $START." 1>&2
        return 1
    fi
    END_FILE=$(obfi_find_log $END)
    if [[ $? -ne 0 ]]; then
        echo "Error: Could not find log file for end timestamp $END." 1>&2
        return 1
    fi

    if [[ "$START_FILE" != "$END_FILE" ]]; then
        echo "Warning: Start and end timestamps in different files. Assuming consecutive." 1>&2
        obfi__file_range "$START_FILE" "$START" "END"
        obfi__file_range "$END_FILE" "START" "$END"
    else
        obfi__file_range "$START_FILE" "$START" "$END"
    fi
}

obfi__file_range() {
    if [[ -z "$1" || -z "$2" || -z "$3" ]]; then
        echo "Usage: obfi__file_range <file> <start> <end>" 1>&2
        echo "" 1>&2
        echo "Prints the logs from the given file in the given range." 1>&2
        echo "Example: obfi__file_range access.log 1748502382753 1748503464280" 1>&2
        echo "Example: obfi__file_range access.log-20250201.gz 1748502382753 END" 1>&2
        echo "Timestamps eg from grafana URLs" 1>&2
        return 1
    fi

    START=$2
    END=$3

    if [[ "$END" == "END" ]]; then
        # Current time in ms
        END=$(date +%s%3N)
    fi

    if [[ "$START" == "START" ]]; then
        START=0
    fi

    echo "Reading logs from $1: $(date -d "@$((START / 1000))" +"%Y-%m-%d %H:%M:%S") to $(date -d "@$((END / 1000))" +"%Y-%m-%d %H:%M:%S") ($START to $END)" 1>&2

    # Handle gzip and non-gzip files
    if [[ "$1" == *.gz ]]; then
        zcat "$1"
    else
        cat "$1"
    fi | python3 -c "
import sys
from datetime import datetime, timezone
start = datetime.fromtimestamp($START / 1000, tz=timezone.utc)
end = datetime.fromtimestamp($END / 1000, tz=timezone.utc)

# Format as nginx dates
start = start.strftime('%d/%b/%Y:%H:%M:%S')
end = end.strftime('%d/%b/%Y:%H:%M:%S')

started = False
buffer = 25  # Lines to read after mismatch
try:
    for line in sys.stdin:
        # Extract the date from the line
        # Get the date part, e.g. '18/Mar/2025:11:20:36 +0000'
        date_str = line.split(' ', 5)[3][1:]

        if start <= date_str <= end:
            started = True
            buffer = 25
            sys.stdout.write(line)
        elif started:
            buffer -= 1
            if buffer == 0:
                break
except BrokenPipeError:
    pass
    "
}

obfi_find_log() {
    if [[ -z "$1" || "$1" == "--help" ]]; then
        echo "Usage: obfi_find_log <timestamp>"
        echo "Finds the file for the given timestamp in ms since the epoch."
        echo "Example: obfi_find_log 1748502382753"
        return 1
    fi

    TS=$1
    LOG_DIR="${OBFI_LOG_DIR:-/1/var/log/nginx}"

    FILES_TO_CHECK=(
        "$LOG_DIR/access.log"
        "$LOG_DIR/access.log-$(date -d "@$((TS / 1000))" +"%Y%m%d").gz"
        # Also check the preceding file, since our logs don't start at 00:00
        "$LOG_DIR/access.log-$(date -d "@$((TS / 1000 - 86400))" +"%Y%m%d").gz"
    )

    for FILE in "${FILES_TO_CHECK[@]}"; do
        # The files are consecutive, so if the first one is not found,
        # we can stop checking further.
        if [[ ! -f "$FILE" ]]; then
            break
        fi

        # Check if in the future
        if [[ "$FILE" == *"access.log" ]]; then
            END=$(tail -n 1 "$FILE" | awk '{print $4}' | sed 's/\[//')
            END=$(obfi__nginx_date_to_iso_date "$END")
            END_TS=$(date -d "$END" +%s)

            if (( TS > END_TS * 1000 )); then
                echo "Timestamp $TS is from the future of the current access.log." 1>&2
                return 1
            fi
        fi

        # Check if the TS is after the start of the log file, which is all that's needed
        # since the logs are consecutively older.
        if [[ "$FILE" == *.gz ]]; then
            START=$(zcat "$FILE" | head -n 1 | awk '{print $4}' | sed 's/\[//')
        else
            START=$(head -n 1 "$FILE" | awk '{print $4}' | sed 's/\[//')
        fi

        START=$(obfi__nginx_date_to_iso_date "$START")
        START_TS=$(date -d "$START" +%s)

        # Check if in the range of the current log file
        if (( TS > START_TS * 1000 )); then
            echo "$FILE"
            return 0
        fi
    done

    echo "No log file found for timestamp $TS." 1>&2
    return 1
}


###############################################################
# Aggregation commands
###############################################################

# The date is in format '[30/Aug/2024:16:00:00 +0000]'
# We extract the date part and then group by the date part
#
# Note these are separate functions so we get tab autocompletion
#
# Note: stdbuf is used to prevent buffering; this allows the commands to
# be used in a pipeline, eg `obfi tac | obfi_count_minute | head`
# Note: For high traffic sites, there might be some bugs, since this assumes
# the input is always cleanly sorted. In reality logs sometimes overlap.
obfi_count_minute() {
    grep -oE ' \[[0-9]{2}.{24}\] ' - | cut -c 3-19 | stdbuf -oL uniq -c
}
obfi_count_hour() {
    grep -oE ' \[[0-9]{2}.{24}\] ' - | cut -c 3-16 | stdbuf -oL uniq -c
}
obfi_count_day() {
    grep -oE ' \[[0-9]{2}.{24}\] ' - | cut -c 3-13 | stdbuf -oL uniq -c
}


# Convert eg "18/Mar/2025:11:20:36 +0000" to "2025-03-18 11:20:36 +0000"
obfi__nginx_date_to_iso_date() {
    DATETIME=$1
    MONTHS=(Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec)
    MONTH_MAP=$(printf "%s " "${MONTHS[@]}" | awk '{for(i=1;i<=NF;i++) printf "%s %02d ", $i, i}')
    echo "$DATETIME" | awk -v MONTH_MAP="$MONTH_MAP" '
    BEGIN {
        split(MONTH_MAP, map, " ")
        for (i = 1; i <= length(map); i += 2) {
            month_map[map[i]] = map[i+1]
        }
    }
    {
        year = substr($0, 8, 4)
        month = month_map[substr($0, 4, 3)]
        day = substr($0, 1, 2)
        time = substr($0, 13, 8)
        tz = substr($0, 22, 6)
        printf "%s-%s-%s %s %s\n", year, month, day, time, tz
    }'
}

obfi_top_ips() {
    COUNT=${1:-25}
    grep -oE '^[0-9.()]+' - | sort | uniq -c | sort -rn | head -n $COUNT
}

obfi_top_http_statuses() {
    grep -oE '" [0-9]{3} ' - | sort | uniq -c | sort -rn
}

obfi_top_bots() {
    obfi_grep_bots -o | \
        tr '[:upper:]' '[:lower:]' | \
        sed 's/[^[:alnum:]\n]/_/g' | \
        sort | uniq -c | sort -rn
}

###############################################################
# Grep commands
###############################################################

obfi_grep_bots() {
    # FIXME: Should be in sync with openlibrary/plugins/openlibrary/code.py
    grep $1 -iE 'ahrefsbot|amazonbot|bingbot|bytespider|claudebot|dataforseobot|discordbot|dotbot|googlebot|gptbot|iaskbot|meta-externalagent|mj12bot|mojeekbot|perplexitybot|petalbot|pinterestbot|qwantbot|semrushbot|seznambot|tiktokspider|ttspider|uptimerobot|yandexaccessibilitybot|yandexbot|yandexrenderresourcesbot' -
}

obfi_grep_secondary_reqs() {
    # Requests that are not very important and that tend to be noisy because they're
    # required by the loading of any normal OL page.
    grep $1 -E '/static|/images|/cdn|partials.json'
}

###############################################################
# Obfuscation commands
###############################################################

obfi_is_listening() {
    ps aux | grep -v grep | grep -q "mktable.py"
    return $?
}

obfi_listen() {
    # listen in the background to build the IP table
    if [[ -z "$SEED_PATH" ]]; then
        echo "Error: SEED_PATH is not set." 1>&2
        exit 1
    fi

    # Check if already running using ps
    if obfi_is_listening; then
        echo "Already listening, restarting..." 1>&2
        obfi_stop_listening
    fi

    # Run with timeout for 5min
    echo "Listening for 1 minute in the background. Run 'obfi_stop_listening' to stop it." 1>&2
    # Start in background subshell
    (
        timeout 1m bash -c "
            sudo tcpdump -i eth0 -n '(dst port 80 or dst port 443) and tcp[tcpflags] & tcp-syn != 0' \
            | sudo -E SEED_PATH=$SEED_PATH /opt/openlibrary/scripts/obfi/mktable.py
        " > /dev/null 2>&1
    ) &
}

obfi_stop_listening() {
    # Stop the listening process

    # Check if already running using ps
    if obfi_is_listening; then
        sudo pkill -f mktable.py
    else
        echo "Not running"
    fi
}

obfi_decode() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        echo "Usage: obfi_decode <ip>"
        echo "Decodes the obfuscated IP address <ip>."
        return 1
    fi

    if [[ -z "$SEED_PATH" ]]; then
        echo "Error: SEED_PATH is not set." 1>&2
        exit 1
    fi

    IP=$1

    if ! obfi_is_listening; then
        echo "Note: obfi not listening. Listening for 60 attempts to decode $IP..." 1>&2
    fi

    sudo -E /opt/openlibrary/scripts/decode_ip.sh "$IP"
}

obfi_decode_all() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        echo "Usage: obfi_decode_all"
        echo "Decodes all IPs in stdin, one per line."
        return 1
    fi

    if [[ -z "$SEED_PATH" ]]; then
        echo "Error: SEED_PATH is not set." 1>&2
        exit 1
    fi

    if ! obfi_is_listening; then
        echo "Obfi is not listening. Starting..." 1>&2
        obfi_listen
    fi

    # Pipe from stdin to reveal.py
    sudo -E /opt/openlibrary/scripts/obfi/reveal.py \
        | sudo -E /opt/openlibrary/scripts/obfi/shownames.py
}

###############################################################
# Graphite commands
# Not documented, but can be used for sending things to graphite.
#
# Example:
#  obfi | obfi_count_minute | obfi_to_graphite_event "openlibrary.web.requests" | obfi_sink_graphite
###############################################################

obfi_to_graphite_event() {
    if [[ -z "$1" || "$1" == "-h" || "$1" == "--help" ]]; then
        echo "Usage: obfi_to_graphite_event <bucket>"
        echo "Converts lines like '   12342 03/Feb/2025:18:17' to the graphite format: 'bucket 12342 1706989020'"
        return 1
    fi

    BUCKET=$1
    # Convert the datetime in formats like 03/Feb/2025:18:17 -> timestamp
    while read LINE; do
        # Lines are of the form "   12342 03/Feb/2025:18:17"
        COUNT=$(echo $LINE | awk '{print $1}')
        DATE=$(echo $LINE | awk '{print $2}')
        DATE=$(obfi__nginx_date_to_iso_date "$DATE")
        TIMESTAMP=$(date -d "$DATE" +"%s")
        echo "$1 $COUNT $TIMESTAMP"
    done
}

obfi_sink_graphite() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        echo "Usage: obfi_sink_graphite"
        echo "Pipes the output of obfi_to_graphite_event to Graphite."
        return 1
    fi
    while read LINE; do
        echo $LINE | tee >(nc -q0 graphite.us.archive.org 2003)
    done
}
