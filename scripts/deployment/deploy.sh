#!/bin/bash

handle_error() {
    echo -e "\n\nERR" >&2
    if [ -n "$TMP_DIR" ]; then
        cleanup "$TMP_DIR"
    fi
    exit 1
}

handle_exit() {
    echo -e "\n\nSIGINT" >&2
    if [ -n "$TMP_DIR" ]; then
        cleanup "$TMP_DIR"
    fi
    exit 1
}

trap 'handle_error' ERR
trap 'handle_exit' SIGINT
set -e

# See https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad
SERVER_SUFFIX=${SERVER_SUFFIX:-""}
SERVER_NAMES=${SERVERS:-"ol-home0 ol-covers0 ol-web0 ol-web1 ol-web2 ol-www0"}
SERVERS=$(echo $SERVER_NAMES | sed "s/ /$SERVER_SUFFIX /g")$SERVER_SUFFIX
IGNORE_CHANGES=${IGNORE_CHANGES:-0}

# Install GNU parallel if not there
# Check is GNU-specific because some hosts had something else called parallel installed
# [[ $(parallel --version 2>/dev/null) = GNU* ]] || sudo apt-get -y --no-install-recommends install parallel

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "jq is not installed. Please follow the instructions on https://jqlang.github.io/jq/download/ to install it."
    exit 1
fi

cleanup() {
    TMP_DIR=$1
    echo ""
    echo "Cleaning up"
    rm -rf $TMP_DIR
}

check_for_local_changes() {
    SERVER=$1
    REPO_DIR=$2

    echo -n "   $SERVER ... "

    OUTPUT=$(ssh $SERVER "cd $REPO_DIR; sudo git status --porcelain --untracked-files=all")

    if [ -z "$OUTPUT" ]; then
        echo "✓"
    elif [ $IGNORE_CHANGES -eq 1 ]; then
        echo "✗ (ignored)"
    else
        echo "✗"
        echo "There are changes in the olsystem repo on $SERVER. Please commit or stash them before deploying."
        echo "Or, set IGNORE_CHANGES=1 to ignore this check."
        ssh -t $SERVER "cd $REPO_DIR; sudo git status --porcelain --untracked-files=all"
        cleanup "$TMP_DIR"
        exit 1
    fi
}

check_server_access() {
    echo ""
    echo "Checking server access..."
    for SERVER in $SERVERS; do
        echo -n "   $SERVER ... "
        DOCKER_ACCESS=$(ssh -o ConnectTimeout=10 $SERVER "sudo usermod -a -G docker \"\$USER\"" && echo "✓" || echo "✗")
        if [ "$DOCKER_ACCESS" == "✓" ]; then
            echo "✓"
        else
            echo "⚠"
            echo "Could not access $SERVER."
            exit 1
        fi
    done
}

copy_to_servers() {
    TAR_PATH="$1"
    DESTINATION="$2"
    DIR_IN_TAR="$3"
    DESTINATION_PARENT=$(dirname $DESTINATION)

    TAR_FILE=$(basename $TAR_PATH)

    echo "Copying to the servers..."
    for SERVER in $SERVERS; do
        echo -n "   $SERVER: Copying ... "
        ssh "$SERVER" "sudo rm -rf $DESTINATION /tmp/$TAR_FILE || true"

        if OUTPUT=$(scp "$TAR_PATH" "$SERVER:/tmp/$TAR_FILE" 2>&1); then
            echo -n "✓."
        else
            echo "⚠"
            echo "$OUTPUT"
            return 1
        fi

        echo -n " Extracting ... "
        if OUTPUT=$(ssh "$SERVER" "sudo tar -xzf /tmp/$TAR_FILE -C $DESTINATION_PARENT" 2>&1); then
            echo "✓"
        else
            echo "⚠"
            echo "$OUTPUT"
            ssh "$SERVER" "sudo rm -rf /tmp/$TAR_FILE"
            return 1
        fi

        # If DIR_IN_TAR is different from the final part of the DESTINATION, move it
        DESTINATION_FINAL=$(basename $DESTINATION)
        if [ "$DIR_IN_TAR" != "$DESTINATION_FINAL" ]; then
            ssh "$SERVER" "
                set -e
                sudo rm -rf $DESTINATION || true
                sudo mv '$DESTINATION_PARENT/$DIR_IN_TAR' $DESTINATION
            " 2>&1
        fi

        ssh "$SERVER" "sudo rm -rf /tmp/$TAR_FILE"
    done
}

deploy_olsystem() {
    echo "Starting $REPO deployment at $(date)"
    echo "Deploying to: $SERVERS"

    check_server_access

    TMP_DIR=${TMP_DIR:-$(mktemp -d)}
    cd $TMP_DIR

    CLEANUP=${CLEANUP:-1}
    CLONE_URL=${CLONE_URL:-"git@github.com:internetarchive/olsystem.git"}
    REPO=${REPO:-"olsystem"}
    REPO_NEW="${REPO}_new"
    REPO_PREVIOUS="${REPO}_previous"

    echo ""
    echo "Checking for changes in the $REPO repo on the servers..."
    for SERVER in $SERVERS; do
        check_for_local_changes $SERVER "/opt/$REPO"
    done
    echo -e "No changes found in the $REPO repo on the servers.\n"

    # Get the latest code
    echo -ne "Cloning $REPO repo ... "
    git clone --depth=1 "$CLONE_URL" $REPO_NEW 2> /dev/null
    echo -n "✔ (SHA: $(git -C $REPO_NEW rev-parse HEAD | cut -c -7))"
    # compress the repo to speed up the transfer
    tar -czf $REPO_NEW.tar.gz $REPO_NEW
    echo " ($(du -h $REPO_NEW.tar.gz | cut -f1) compressed)"

    if ! copy_to_servers "$TMP_DIR/$REPO_NEW.tar.gz" "/opt/$REPO_NEW" "$REPO_NEW"; then
        cleanup "$TMP_DIR"
        exit 1
    fi

    echo ""
    echo "Final swap..."
    for SERVER in $SERVERS; do
        echo -n "   $SERVER ... "

        if OUTPUT=$(ssh $SERVER "
            set -e
            sudo chown -R root:staff /opt/$REPO_NEW
            sudo chmod -R g+rwX /opt/$REPO_NEW

            sudo rm -rf /opt/$REPO_PREVIOUS || true
            sudo mv /opt/$REPO /opt/$REPO_PREVIOUS
            sudo mv /opt/$REPO_NEW /opt/$REPO
        "); then
            echo "✓"
        else
            echo "⚠"
            echo "$OUTPUT"
            cleanup "$TMP_DIR"
            exit 1
        fi
    done

    echo "Finished $REPO deployment at $(date)"
    echo "To reboot the servers, please run scripts/deployments/restart_all_servers.sh"
    if [ $CLEANUP -eq 1 ]; then
        cleanup "$TMP_DIR"
    fi
}

date_to_timestamp() {
    # Check if Mac
    if [ "$(uname)" == "Darwin" ]; then
        # Remove the milliseconds
        DATE_STRING=$(echo $1 | sed 's/\.[0-9]*//')
        # Replace the Z with +0000
        DATE_STRING=$(echo $DATE_STRING | sed 's/Z/+0000/')
        # Replace a colon in the timezone with nothing
        DATE_STRING=$(echo $DATE_STRING | sed 's/:\([0-9][0-9]\)$/\1/')

        date -j -f "%FT%T%z" "$DATE_STRING" +%s
    else
        date -d "$1" +%s
    fi
}

deploy_openlibrary() {
    COMPOSE_FILE="/opt/openlibrary/compose.yaml:/opt/openlibrary/compose.production.yaml"
    TMP_DIR=$(mktemp -d)

    cd $TMP_DIR
    echo -ne "Cloning openlibrary repo ... "
    git clone --depth=1 "https://github.com/internetarchive/openlibrary.git" openlibrary 2> /dev/null
    GIT_SHA=$(git -C openlibrary rev-parse HEAD | cut -c -7)
    echo "✔ (SHA: $GIT_SHA)"
    echo ""

    # Assert latest docker image is up-to-date
    IMAGE_META=$(curl -s https://hub.docker.com/v2/repositories/openlibrary/olbase/tags/latest)
    # eg 2024-11-26T19:28:20.054992Z
    IMAGE_LAST_UPDATED=$(echo $IMAGE_META | jq -r '.last_updated')
    # eg 2024-11-27T16:38:13-08:00
    GIT_LAST_UPDATED=$(git -C openlibrary log -1 --format=%cd --date=iso-strict)
    IMAGE_LAST_UPDATED_TS=$(date_to_timestamp $IMAGE_LAST_UPDATED)
    GIT_LAST_UPDATED_TS=$(date_to_timestamp $GIT_LAST_UPDATED)

    if [ $GIT_LAST_UPDATED_TS -gt $IMAGE_LAST_UPDATED_TS ]; then
        echo "✗ Docker image is not up-to-date"
        echo -e "Go to https://github.com/internetarchive/openlibrary/actions/workflows/olbase.yaml and click on 'Run workflow' to build the latest image for the master branch.\n\nThen run this script again."
        cleanup $TMP_DIR
        exit 1
    else
        echo "✓ Docker image is up-to-date"
    fi

    check_server_access

    echo "Checking for changes in the openlibrary repo on the servers..."
    for SERVER in $SERVERS; do
        check_for_local_changes $SERVER "/opt/openlibrary"
    done
    echo -e "No changes found in the openlibrary repo on the servers.\n"

    mkdir -p openlibrary_new
    cp -r openlibrary/compose*.yaml openlibrary_new
    cp -r openlibrary/docker openlibrary_new
    tar -czf openlibrary_new.tar.gz openlibrary_new
    if ! copy_to_servers "$TMP_DIR/openlibrary_new.tar.gz" "/opt/openlibrary" "openlibrary_new"; then
        cleanup "$TMP_DIR"
        exit 1
    fi
    echo ""

    # Fix file ownership + Make into a git repo so can easily track local mods
    for SERVER in $SERVERS; do
        ssh $SERVER "
            set -e
            sudo chown -R root:staff /opt/openlibrary
            sudo chmod -R g+rwX /opt/openlibrary
            cd /opt/openlibrary
            sudo git init 2>&1 > /dev/null
            sudo git add . > /dev/null
            sudo git commit -m 'Deployed openlibrary' > /dev/null
        "
    done

    echo "Prune docker images/cache..."
    for SERVER in $SERVERS; do
        echo -n "   $SERVER ... "
        # ssh $SERVER "docker image prune -f"
        if OUTPUT=$(ssh $SERVER "docker image prune -f && docker builder prune -f" 2>&1); then
            echo "✓"
        else
            echo "⚠"
            echo "$OUTPUT"
            cleanup "$TMP_DIR"
            exit 1
        fi
    done
    echo ""

    echo "Pull the latest docker images..."
    # We need to fetch by the exact image sha, since the registry mirror on the prod servers
    # has a cache which means fetching the `latest` image could be stale.
    OLBASE_DIGEST=$(echo $IMAGE_META | jq -r '.images[0].digest')
    for SERVER in $SERVERS; do
        echo "   $SERVER ... "
        ssh -t $SERVER "
            set -e;
            docker pull openlibrary/olbase@$OLBASE_DIGEST
            echo 'FROM openlibrary/olbase@$OLBASE_DIGEST' | docker build --tag openlibrary/olbase:latest -f - .
            COMPOSE_FILE='$COMPOSE_FILE' HOSTNAME=\$HOSTNAME docker compose --profile $SERVER pull
        "
        echo "   ... $SERVER ✓"
    done

    echo "Finished production deployment at $(date)"
    echo "To reboot the servers, please run scripts/deployments/restart_all_servers.sh"

    cleanup $TMP_DIR
}

# Clone booklending utils
# parallel --quote ssh {1} "echo -e '\n\n{}'; if [ -d /opt/booklending_utils ]; then cd {2} && sudo git pull git@git.archive.org:jake/booklending_utils.git master; fi" ::: $SERVERS ::: /opt/booklending_utils

# And tag the deploy!
# DEPLOY_TAG="deploy-$(date +%Y-%m-%d)"
# sudo git tag $DEPLOY_TAG
# sudo git push git@github.com:internetarchive/openlibrary.git $DEPLOY_TAG


# Supports:
# - deploy.sh olsystem
# - deploy.sh openlibrary

if [ "$1" == "olsystem" ]; then
    deploy_olsystem
elif [ "$1" == "openlibrary" ]; then
    deploy_openlibrary
else
    echo "Usage: $0 [olsystem|openlibrary]"
    exit 1
fi
