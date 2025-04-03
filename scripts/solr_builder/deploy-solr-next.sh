#!/bin/bash

# NOTE: Not fully tested, needs to be run line-by-line for a bit to make sure everything still
# works, especially in our new proxy world!

SOLR_PROD_SERVER="ol-solr0"
SOLR_BUILDER_SERVER="ol-solr1"

# Error if slack token not set
if [ -z "$SLACK_TOKEN" ]; then
    echo "SLACK_TOKEN not set"
    exit 1
fi

##
# helpers
##
source ./scripts/solr_builder/utils.sh

send_slack_message "#openlibrary-g" "
    Beep boop! Heads up moving solr from incubation to its production server. Process should take ~1.5 hours.
    Let me know if you notice any issues! (CC @cdrini)
"

echo "1. Switching everything to ol-solr0"
switch_all_web_to_solr $SOLR_PROD_SERVER
test_all_ol_search # Confirm everything is working
if [ $? -ne 0 ]; then
    echo "ERROR: $SOLR_PROD_SERVER is not working"
    exit 1
fi

# 2. Dump ol-solr1
./scripts/solr_builder/dump-solr.sh $SOLR_BUILDER_SERVER

# 3. Switch everything to ol-solr1
switch_all_web_to_solr $SOLR_BUILDER_SERVER
test_all_ol_search # Confirm everything is working
if [ $? -ne 0 ]; then
    echo "ERROR: $SOLR_BUILDER_SERVER is not working"
    exit 1
fi

# 4. Backup prod/old solr
./scripts/solr_builder/dump-solr.sh $SOLR_PROD_SERVER

# 5. Load ol-solr1 data on ol-solr0

# Require prompt before continuing
wait_yn "Ready to begin deleting solr?"

./scripts/solr_builder/restore-solr.sh $SOLR_PROD_SERVER $SOLR_BUILDER_SERVER

# 6. Switch everything to ol-solr0

# Confirm on ol-dev1 first
switch_web_to_solr ol-dev1 $SOLR_PROD_SERVER
test_ol_search 'testing.openlibrary.org'

# Now let's go full throttle!
switch_all_web_to_solr $SOLR_PROD_SERVER
test_all_ol_search # Confirm everything is working

send_slack_message "#openlibrary-g" "
    Ok, solr moved over, and production now connected to it! Note it's catching up on edits done
    since the start of this, but should be done soon :+1: Let me know if you notice
    anything off! (cc @cdrini @seabelis)
"
