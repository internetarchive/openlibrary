#!/bin/bash

# usage: ./scripts/deployment/patchdeploy.sh 1234

# Check if PR number is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <pr_number>"
    exit 1
fi

PR_NUMBER=$1
PATCH_URL="https://patch-diff.githubusercontent.com/raw/internetarchive/openlibrary/pull/${PR_NUMBER}.diff"
echo "Note: Patch Deploys cannot rebuild js/css"

# Iterate over hosts
SERVERS=${SERVERS:-"ol-web0 ol-web1 ol-web1 ol-www0"}

for host in $SERVERS; do
    echo "Applying patch on ${host}.us.archive.org..."

    # Determine container name based on host
    if [[ "$host" == "ol-www0" ]]; then
        CONTAINER="openlibrary-web_nginx-1"
    else
        CONTAINER="openlibrary-web-1"
    fi

    ssh -T "${host}.us.archive.org" <<EOF
    set -e  # Exit immediately if any command fails

    cd /opt/openlibrary
    export HTTPS_PROXY=http://http-proxy.us.archive.org:8080

    if curl -sSL --compressed "${PATCH_URL}" | tee >(cat) | tee >(git apply --check) | git apply; then
        echo "Patch is applicable, applying..."
        echo "Patch applied successfully, restarting ${CONTAINER} on ${host}."
        docker restart ${CONTAINER}
    else
        echo "Patch already applied or not applicable cleanly — skipping patch on ${host}."
    fi
    echo "# ================="
    echo "# FINISHING ${host}"
    echo "# ================="
EOF

    if [ $? -ne 0 ]; then
        echo "Error encountered on ${host}. Stopping execution."
        exit 1
    fi

done

echo "Patch successfully applied on all web nodes."
