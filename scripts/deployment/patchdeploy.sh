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
# Iterate over webnode_id [0, 1, 2]
for webnode_id in {0..2}; do
    echo "Applying patch on ol-web${webnode_id}.us.archive.org..."

    ssh mek@ol-web${webnode_id}.us.archive.org <<EOF
        set -e  # Exit immediately if any command fails
        PATCH_CMD='docker exec -i openlibrary-web-1 bash -c "HTTPS_PROXY=http://http-proxy.us.archive.org:8080 curl -sS ${PATCH_URL} | git apply"'

        if eval "\$PATCH_CMD"; then
            echo "Patch applied successfully on ol-web${webnode_id}, restarting container..."
            docker restart openlibrary-web-1
        else
            echo "Failed to apply patch on ol-web${webnode_id}. Exiting..."
            exit 1
        fi
EOF

    if [ $? -ne 0 ]; then
        echo "Error encountered on ol-web${webnode_id}. Stopping execution."
        exit 1
    fi

done

echo "Patch successfully applied on all web nodes."
