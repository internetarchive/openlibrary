#!/bin/bash

# usage: ./scripts/deployment/patchdeploy.sh 1234

# Check if PR number is provided
if [[ -z "$1" || "$1" == "--help" ]]; then
    echo "This script applies a patch from a GitHub PR to the Open Library servers."
    echo ""
    echo "Usage: $0 <pr_number|patch_url>"
    echo ""
    echo "Environment variables:"
    echo "  SERVERS=ol-web0 ol-web1 ol-web2  List of servers to apply the patch to."
    echo "  PATCH_ON=host|container          Whether to apply the patch on the host or inside"
    echo "                                   the container."
    echo "                                   Default: container unless patching www nginx changes"
    echo "  SERVICE=container_name           Default: web for ol-web hosts, web_nginx for ol-www0"
    echo "  APPLY_OPTIONS=''                 Options to pass to git apply. E.g. use -R to"
    echo "                                   un-apply a patch. See 'git apply --help' for options."
    echo "  RESET=''                         If 'true', resets the container before applying the patch."
    echo "  MAKE=''                          If specified, runs the provided 'make' commands inside the container."
    echo "                                   E.g. MAKE='js css components' to rebuild all front-end assets."
    exit 1
fi

if [[ "$1" == https* ]]; then
    PATCH_URL="$1"
else
    PATCH_URL="https://patch-diff.githubusercontent.com/raw/internetarchive/openlibrary/pull/${1}.diff"
fi
echo "Note: Patch Deploys cannot rebuild js/css"
echo

# Iterate over hosts
SERVERS=${SERVERS:-"ol-web0 ol-web1 ol-web2"}
PROXY="http://http-proxy.us.archive.org:8080"
APPLY_OPTIONS=${APPLY_OPTIONS:-""}

echo "Applying patch ${PATCH_URL} to ${SERVERS}:"

for host in $SERVERS; do
    # Determine default container name based on host
    if [[ "$host" == "ol-www0" ]]; then
        SERVICE=${SERVICE:-"web_nginx"}
        if [[ "$SERVICE" == "web_nginx" ]]; then
            # If deploying nginx configs, must apply only to host
            PATCH_ON=${PATCH_ON:-host}
        else
            PATCH_ON=${PATCH_ON:-container}
        fi
    else
        PATCH_ON=${PATCH_ON:-container}
        SERVICE=${SERVICE:-"web"}
    fi

    TMP_OUTPUT_FILE=$(mktemp)
    STATUS=0
    if [ "$PATCH_ON" == "host" ]; then
        if [ -n "$MAKE" ]; then
            echo "Error: MAKE is not supported when PATCH_ON is set to host."
            exit 1
        fi

        echo -n "  $host ... "
        ssh ${host}.us.archive.org "
            set -e
            cd /opt/openlibrary
            HTTPS_PROXY=${PROXY} curl -sL "${PATCH_URL}" | git apply $APPLY_OPTIONS
        " > $TMP_OUTPUT_FILE
        STATUS=$?
    else
        echo -n "  $host / $SERVICE ..."

        if [ "$RESET" == "true" ]; then
            echo -n " recreating ... "
            ssh ${host}.us.archive.org "
                export COMPOSE_FILE='/opt/openlibrary/compose.yaml:/opt/openlibrary/compose.production.yaml'
                export HOSTNAME=\$HOSTNAME
                docker compose up -d --no-deps --force-recreate ${SERVICE} 2>&1
            " > $TMP_OUTPUT_FILE

            if [ $? -eq 0 ]; then
                echo -n '✓'
                rm $TMP_OUTPUT_FILE
            else
                echo -n '✗'
                cat $TMP_OUTPUT_FILE
                rm $TMP_OUTPUT_FILE
                exit 1
            fi
        fi

        echo -n " applying patch ... "
        MAKE_CMD=""
        if [ -n "$MAKE" ]; then
            MAKE_CMD="make $MAKE"
        fi

        ssh ${host}.us.archive.org "
            set -e
            export COMPOSE_FILE='/opt/openlibrary/compose.yaml:/opt/openlibrary/compose.production.yaml'
            export HOSTNAME=\$HOSTNAME
            docker compose exec ${SERVICE} bash -c '
                HTTPS_PROXY=${PROXY} curl -sL ${PATCH_URL} | git apply $APPLY_OPTIONS
                $MAKE_CMD
            ' 2>&1
        " > $TMP_OUTPUT_FILE

        STATUS=$?
    fi

    if [ $STATUS -eq 0 ]; then
        rm $TMP_OUTPUT_FILE

        echo -n '✓ restarting ... '
        ssh ${host}.us.archive.org "
            export COMPOSE_FILE='/opt/openlibrary/compose.yaml:/opt/openlibrary/compose.production.yaml'
            export HOSTNAME=\$HOSTNAME
            docker compose restart ${SERVICE} 2>&1
        " > $TMP_OUTPUT_FILE

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
