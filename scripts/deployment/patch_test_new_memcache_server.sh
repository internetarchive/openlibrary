#!/bin/bash

# CAUTION: This script restarts production servers!

# From https://github.com/internetarchive/olsystem/pull/145
# When we add a new memcached server (currently ol-mem{0,1,2}) we want to test if
# our production servers will properly detect and and use that new memcache server.

# BEFORE RUNNING THIS SCRIPT: Edit the two curl commands below to update the PR
# numbers and tokens.  Also, ensure that list of hosts corresponds to the servers
# that are currently connecting to the ol-mem servers.

# Exit if an error occurs
set -e

# Adjust the PR number and token!!
for node in ol-home0 ol-web1 ol-web2 ol-covers0; do
    ssh $node "
        cd /opt/olsystem
        curl 'https://patch-diff.githubusercontent.com/raw/internetarchive/olsystem/pull/145.diff?token=ABPWKCUDSAEHNTDZTWG2YBDBTPT7I' | sudo git apply
    "
done

for node in ol-home0 ol-web1 ol-web2 ol-covers0; do
    ssh $node "
        cd /opt/olsystem
        sudo git status
    "
done

ssh ol-web1 "docker restart openlibraryweb1"
ssh ol-web2 "docker restart openlibraryweb1"
# Adjust for covers deploy replicas
ssh ol-covers0 "docker restart openlibrarycovers1 openlibrarycovers2 openlibrarycoversnginx1"
ssh ol-home0 "docker restart openlibraryinfobase1 openlibraryinfobasenginx1"

exit

# =====

# If need to revert
for node in ol-home0 ol-web1 ol-web2 ol-covers0; do
    ssh $node "
        cd /opt/olsystem curl 'https://patch-diff.githubusercontent.com/raw/internetarchive/olsystem/pull/145.diff?token=ABPWKCUDSAEHNTDZTWG2YBDBTPT7I' | sudo git apply -R
    "
done

# Run restart stuff above
