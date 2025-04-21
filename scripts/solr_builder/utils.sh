# Example: send_slack_message "@openlibrary-g" "Hello world"
# This is a slackbot currently owned by @cdrini
send_slack_message() {
    # Note channel must include e.g. "#" at start
    local channel=$1
    local message=$2

    echo "Slack message to $channel: $message"
    curl -X POST \
        -H "Content-type: application/json; charset=utf-8" \
        -H "Authorization: Bearer $SLACK_TOKEN" \
        --data "{\"channel\": \"$channel\", \"link_names\": true, \"text\": \"$message\"}" \
        "https://slack.com/api/chat.postMessage"
}

# Ensure the given server returns results for a basic search
test_ol_search() {
    local base_url=$1
    # Split into host and port
    local host=${base_url%:*}
    local port=${base_url#*:}
    local req="/search.json?q=hello&mode=everything&limit=0"

    # Check if '.' in host
    if [[ $host != *"."* ]]; then
        # It's an OL server we have to ssh into
        RESP=$(
            ssh $(ol_server $host) "
                set -e
                curl -s 'http://localhost:${port}$req'
            "
        )
        EXIT_CODE=$?
    else
        # It's a public OL server
        RESP=$(curl -s "http://${base_url}${req}")
        EXIT_CODE=$?
    fi

    # Exit if curl errored
    if [ $EXIT_CODE -ne 0 ]; then
        echo "ERROR: ${base_url} is unreachable"
        return 1
    fi

    # Exit if response is empty
    if [[ $RESP = *"\"numFound\": 0"* ]]; then
        echo "ERROR: ${base_url} is returning 0 results"
        return 1
    fi
}

test_all_ol_search() {
    echo "Test search on all servers returning results"
    for base in ol-web{0..2}:8080 'openlibrary.org' 'testing.openlibrary.org' 'staging.openlibrary.org'; do
        echo -n "  Testing $base ... "
        test_ol_search $base
        if [ $? -eq 0 ]; then
            echo "✓"
        else
            echo "✗"
            return 1
        fi
    done
}

# Show a looping y/n prompt
wait_yn() {
    local prompt=$1

    while true; do
        read -p "$prompt (y/n) " yn
        case $yn in
            [Yy]* ) break;;
            [Nn]* ) exit;;
            * ) ;;
        esac
    done
}

ol_server() {
    local name=$1

    # Add .us.archive.org if not already there
    if [[ $name != *".us.archive.org" ]]; then
        name="${name}.us.archive.org"
    fi

    echo "$name"
}

# Modifies an openlibrary web node's config file to point to the prod solr,
# restarts the web container, and then tests it's getting results
switch_web_to_solr() {
    local node=$1
    local solr=$2

    ssh $(ol_server $node) "
        set -e

        # Replace solr next with prod in config file
        sed -i 's|http://ol-solr.|http://${solr}|g' /opt/olsystem/etc/openlibrary.yml

        # Confirm the new solr is in the config file
        grep -q 'http://${solr}' /opt/olsystem/etc/openlibrary.yml
        if [ \$? -ne 0 ]; then
            echo 'ERROR: Solr not updated in config file'
            exit 1
        fi

        # Restart web container
        docker restart openlibrary-web-1 > /dev/null
    "

    return $? # Return the exit code of the ssh command
}

switch_all_web_to_solr() {
    local solr=$1
    for node in ol-web{0..2} ol-dev1; do
        echo -n "  $node ... "
        switch_web_to_solr $node $solr

        if [ $? -eq 0 ]; then
            echo "✓"
        else
            echo "✗"
            exit 1
        fi
    done

    echo -n "Waiting for everything to restart ... "
    sleep 15 # Wait for everything to restart
    echo "✓"
}
