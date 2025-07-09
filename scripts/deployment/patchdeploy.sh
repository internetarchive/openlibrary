#!/bin/bash

# usage: ./scripts/deployment/patchdeploy.sh 1234

# Check if PR number is provided
if [[ -z "$1" || "$1" == "--help" ]]; then
    echo "This script applies a patch from a GitHub PR to the Open Library servers."
    echo ""
    echo "Usage: $0 <pr_number>"
    echo ""
    echo "Environment variables:"
    echo "  SERVERS=ol-web0 ol-web1 ol-web2  List of servers to apply the patch to."
    echo "  PATCH_ON=host|container          Whether to apply the patch on the host or inside"
    echo "                                   the container."
    echo "                                   Default: container unless patching www nginx changes"
    echo "  CONTAINER=container_name         Default: openlibrary-web-1 for ol-web hosts,"
    echo "                                   openlibrary-web_nginx-1 for ol-www0"
    echo "  APPLY_OPTIONS=''                 Options to pass to git apply. E.g. use -R to"
    echo "                                   un-apply a patch. See 'git apply --help' for options."
    exit 1
fi

PR_NUMBER=$1
PATCH_URL="https://patch-diff.githubusercontent.com/raw/internetarchive/openlibrary/pull/${PR_NUMBER}.diff"
echo "Note: Patch Deploys cannot rebuild js/css"
echo

# Iterate over hosts
SERVERS=${SERVERS:-"ol-web0 ol-web1 ol-web2"}
PROXY="http://http-proxy.us.archive.org:8080"
APPLY_OPTIONS=${APPLY_OPTIONS:-""}

echo "Applying patch #${PR_NUMBER} to ${SERVERS}:"

for host in $SERVERS; do
    # Determine default container name based on host
    if [[ "$host" == "ol-www0" ]]; then
        CONTAINER=${CONTAINER:-"openlibrary-web_nginx-1"}
        if [[ "$CONTAINER" == "openlibrary-web_nginx-1" ]]; then
            # If deploying nginx configs, must apply only to host
            PATCH_ON=${PATCH_ON:-host}
        else
            PATCH_ON=${PATCH_ON:-container}
        fi
    else
        PATCH_ON=${PATCH_ON:-container}
        CONTAINER=${CONTAINER:-"openlibrary-web-1"}
    fi

    TMP_OUTPUT_FILE=$(mktemp)
    STATUS=0
    if [ "$PATCH_ON" == "host" ]; then
        echo -n "  $host ... "
        ssh ${host}.us.archive.org "
            set -e
            cd /opt/openlibrary
            HTTPS_PROXY=${PROXY} curl -sL "${PATCH_URL}" | git apply $APPLY_OPTIONS
        " > $TMP_OUTPUT_FILE
        STATUS=$?
    else
        echo -n "  $host $CONTAINER ... "
        ssh ${host}.us.archive.org "
            docker exec ${CONTAINER} bash -c '
                HTTPS_PROXY=${PROXY} curl -sL ${PATCH_URL} | git apply $APPLY_OPTIONS
            ' 2>&1
        " > $TMP_OUTPUT_FILE
        STATUS=$?
    fi

    if [ $STATUS -eq 0 ]; then
        rm $TMP_OUTPUT_FILE

        echo -n '✓. Restarting ... '
        ssh ${host}.us.archive.org "docker restart ${CONTAINER} 2>&1" > $TMP_OUTPUT_FILE
        if [ $? -eq 0 ]; then
            echo '✓'
            rm $TMP_OUTPUT_FILE
        else
            echo '✗'
            cat $TMP_OUTPUT_FILE
            rm $TMP_OUTPUT_FILE
            exit 1
        fi
    else
        echo '✗ (Skipping)'
        cat $TMP_OUTPUT_FILE
        rm $TMP_OUTPUT_FILE
    fi
done
