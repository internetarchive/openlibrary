#!/usr/bin/env bash

# NOTE: Not fully tested, needs to be run line-by-line for a bit to make sure everything still
# works, especially in our new proxy world!
# NOTE: RUN IN TMUX!!!!

SLACK_TOKEN=""
SOLR_PROD_SERVER=ol-solr0
SOLR_BUILDER_SERVER=ol-solr1
ORCHESTRATION_SERVER=ol-home0

# Error if slack token not set
if [ -z "$SLACK_TOKEN" ]; then
    echo "SLACK_TOKEN not set"
    return 1
fi

##
# helpers
##

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

    RESP=$(curl -s "http://${base_url}/search.json?q=hello&mode=everything&limit=0")
    # Exit if curl errored
    if [ $? -ne 0 ]; then
        echo "ERROR: ${base_url} is unreachable"
        return 1
    fi

    # Exit if response is empty
    if [[ $RESP = *"\"numFound\": 0"* ]]; then
        echo "ERROR: ${base_url} is returning 0 results"
        return 1
    fi

    echo "SUCCESS: ${base_url} is returning results"
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

# Modifies an openlibrary web node's config file to point to the prod solr,
# restarts the web container, and then tests it's getting results
test_webnode_with_prod_solr() {
    local node=$1

    ssh -A $node "
        # Replace solr next with prod in config file
        sed -i 's/${SOLR_BUILDER_SERVER}/${SOLR_PROD_SERVER}/g' /opt/olsystem/etc/openlibrary.yml

        # Restart web container
        docker restart openlibrary-web-1
    "

    # Wait for it to come up
    sleep 15

    test_ol_search "$node:8080"
    if [ $? -ne 0 ]; then
        send_slack_message "#team-abc" "Uh-oh! Search on $node:8080 looks off; can you check @cdrini?"
        wait_yn "Continue?"
    fi
}

send_slack_message "#openlibrary-g" "
    Beep boop! Heads up moving solr from incubation to its production server. Process should take ~1.5 hours.
    Let me know if you notice any issues! (CC @cdrini)
"


##
# Cleanup solr currently on prod server
##

# Stop prod's solr-updater
ssh -A $ORCHESTRATION_SERVER "docker stop openlibrary-solr-updater-1 || true"

# Stop prod's solr
ssh -A $SOLR_PROD_SERVER "docker stop openlibrary-solr-1 || true"

# Make sure search still working
for base in 'ol-web0:8080' 'ol-web1:8080' 'ol-web2:8080' 'openlibrary.org' 'testing.openlibrary.org' 'staging.openlibrary.org'; do
    test_ol_search $base
    if [ $? -ne 0 ]; then
        exit 1
    fi
done

##
# Dump solr on next server
##

send_slack_message "#openlibrary-g" "
    Heads up: edits won't be reflected in search results for the next ~60 minutes (CC @seabelis @cdrini)
"

# Pause solr next updater and note position
ssh -A $ORCHESTRATION_SERVER "
    docker stop openlibrary-solr-next-updater-1 || true
    docker run --rm \
        --volumes-from openlibrary-solr-next-updater-1 \
        ubuntu:xenial \
        cp solr-updater-data/solr-next-update.offset solr-updater-data/_solr-next-update.offset
"

echo "Committing any transient changes into solr before dumping... (takes ~30s)"
time curl "${SOLR_BUILDER_SERVER}:8984/solr/openlibrary/update?commit=true"

echo "Beginning dump (took 1h30 minutes 2024-08)"
date
DUMP_FILE="solrbuilder-$(date +%Y-%m-%d).tar.gz"
time ssh -A $SOLR_BUILDER_SERVER "
    docker run --rm \
        --volumes-from solr_builder-solr_prod-1 \
        -v /tmp/solr:/backup \
        ubuntu:xenial \
        tar czf /backup/$DUMP_FILE /var/solr
"
# Should be ~39G
ssh -A $SOLR_BUILDER_SERVER "du -sh /tmp/solr/$DUMP_FILE"

# REMOVE:
# # Resume solr next updater
# # This will mean edits are reflected while we do the next few steps,
# # but will be missing from the prod solr once it goes up. But that's ok,
# # because we noted the offset! So we'll just start prod's solr-updater at the offset.
# ssh -A $ORCHESTRATION_SERVER "docker start openlibrary-solr-next-updater-1"

# send_slack_message "#openlibrary-g" "Ok, edits should now be being reflected again; note work is still ongoing though (CC @seabelis @cdrini)"

echo "Copy over to prod server (took 8 min 2024-08)"
date
ssh -A $SOLR_PROD_SERVER "mkdir /tmp/solr || true"
time scp $SOLR_BUILDER_SERVER:/tmp/solr/$DUMP_FILE $SOLR_PROD_SERVER:/tmp/solr/$DUMP_FILE

# Require prompt before continuing
wait_yn "Ready to begin deleting solr?"

# Remove containers/volumes/images
ssh -A $SOLR_PROD_SERVER "
    cd /opt/openlibrary
    export COMPOSE_FILE='compose.yaml:compose.production.yaml'
    docker compose --profile ol-solr0 down
"

# TODO: Dump the prod solr as well, and upload both staging/prod to IA as a backup

ssh -A $SOLR_PROD_SERVER "docker container ls -a && docker container prune -f && docker container ls -a"
ssh -A $SOLR_PROD_SERVER "docker volume ls && docker volume prune -f --filter all=1 && docker volume ls" # gulp!
ssh -A $SOLR_PROD_SERVER "docker image ls && docker image prune -f -a && docker image ls"

# Get latest master on server
ssh -A $SOLR_PROD_SERVER "cd /opt/openlibrary && sudo git status"
ssh -A $SOLR_PROD_SERVER "cd /opt/openlibrary && sudo git checkout master && sudo git pull origin master && sudo make git"

echo "Load solr dump into prod server (took 20 minutes on 2024-08)"
date
time ssh -A $SOLR_PROD_SERVER "
    docker run \
        -v openlibrary_solr-data:/var/solr \
        -v /tmp/solr:/backup ubuntu:xenial \
        tar xzf /backup/$DUMP_FILE
"

# note using single quotes so variable expansion doesn't happen here, but
# on the other server (so HOSTNAME is correct)
echo "Bringing it up up up!"
ssh -A $SOLR_PROD_SERVER '
    export COMPOSE_FILE="compose.yaml:compose.production.yaml"
    cd /opt/openlibrary
    HOSTNAME="$HOSTNAME" docker compose --profile ol-solr0 up -d
'

# Wait a bit for it to warm up
sleep 10

# Place on testing to confirm
test_webnode_with_prod_solr ol-dev1

# >>> YOU ARE HERE <<<
# Restart its solr-updater, resuming from previous offset
send_slack_message "#team-abc" "@cdrini Can you update the compose.production.yaml solr-updater so that it's using solr-next settings?"
wait_yn "Continue?"
ssh -A $ORCHESTRATION_SERVER '
    docker run --rm \
        --volumes-from openlibrary-solr-next-updater-1 \
        ubuntu:xenial \
        cp solr-updater-data/_solr-next-update.offset solr-updater-data/solr-update.offset

    cd /opt/openlibrary
    export COMPOSE_FILE="compose.yaml:compose.production.yaml"
    HOSTNAME="$HOSTNAME" docker compose up -d --no-deps solr-updater
'

send_slack_message "#team-abc" "
    Ok, I started prod's solr-updater ; can you check its logs, @cdrini?
    (It's `docker logs --tail=10 -f openlibrary-solr-updater-1`)
"
wait_yn "Continue?"

# Restart the prod web nodes!
test_webnode_with_prod_solr ol-web0
test_webnode_with_prod_solr ol-web1
test_webnode_with_prod_solr ol-web2

send_slack_message "#openlibrary-g" "
    Ok, solr moved over, and production now connected to it! Note it's catching up on edits done
    since the start of this, but should be done soon :+1: Let me know if you notice
    anything off! (cc @cdrini @seabelis)
"
