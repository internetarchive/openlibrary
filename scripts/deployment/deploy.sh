#!/bin/bash

clean_exit() {
    if [ -n "$TMP_DIR" ]; then
        cleanup "$TMP_DIR"
    fi
    exit 1
}

handle_error() {
    echo -e "\n\nERR" >&2
    clean_exit
}

handle_exit() {
    echo -e "\n\nSIGINT" >&2
    clean_exit
}

trap 'handle_error' ERR
trap 'handle_exit' SIGINT
set -e

# See https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SUFFIX=${SERVER_SUFFIX:-".us.archive.org"}
SERVER_NAMES=${SERVERS:-"ol-home0 ol-covers0 ol-web0 ol-web1 ol-web2 ol-www0"}
SERVERS=$(echo $SERVER_NAMES | sed "s/ /$SERVER_SUFFIX /g")$SERVER_SUFFIX
KILL_CRON=${KILL_CRON:-""}
LATEST_TAG=$(curl -s https://api.github.com/repos/internetarchive/openlibrary/releases/latest | sed -n 's/.*"tag_name": "\([^"]*\)".*/\1/p')
RELEASE_DIFF_URL="https://github.com/internetarchive/openlibrary/compare/$LATEST_TAG...master"
DEPLOY_TAG="deploy-$(date +%Y-%m-%d-at-%H-%M)"

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

# Show a looping y/n prompt
wait_yn() {
    local prompt=$1

    while true; do
        read -p "$prompt (y/n) " yn
        case $yn in
            [Yy]* ) break;;
            [Nn]* ) clean_exit;;
            * ) ;;
        esac
    done
}

check_crons() {
    # Check if any critical cron jobs are running:
    CRITICAL_JOBS="oldump.sh|process_partner_data.sh|update_stale_work_references.py|promise_batch_imports.py"

    echo ""
    echo -n "Checking for running critical cron jobs... "
    RUNNING_CRONS=$(ssh ol-home0.us.archive.org ps -ef | grep -v grep | grep -E "$CRITICAL_JOBS" || true)

    # If KILL_CRON is an empty string and there are running jobs, exit early
    if [ -z "$KILL_CRON" ] && [ -n "$RUNNING_CRONS" ]; then
        echo "✗"
        echo "Critical cron jobs are currently running. Halting deployment:"
        echo "$RUNNING_CRONS"
        echo ""
        echo "Set KILL_CRON=1 and run script again to override."
        echo ""
        exit 1
    else
        echo "✓"
    fi
}

check_for_local_changes() {
    SERVER=$1
    REPO_DIR=$2

    echo -n "   $SERVER ... "

    OUTPUT=$(ssh $SERVER "cd $REPO_DIR; sudo git status --porcelain --untracked-files=all")

    if [ -z "$OUTPUT" ]; then
        echo "✓"
    else
        echo "✗"
        echo "There are changes in the olsystem repo on $SERVER. Please commit or stash them, or they will be blown away."
        ssh -t $SERVER "
            cd $REPO_DIR
            sudo git status --porcelain --untracked-files=all
            echo ''
            sudo git diff
        "

        wait_yn "Ignore changes and continue?"
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
    echo "[Now] Starting $REPO deployment at $(date)"
    echo "Deploying to: $SERVERS"

    check_server_access
    check_crons

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
    echo "[Info] To reboot the servers, please run scripts/deployments/restart_all_servers.sh"
    if [ $CLEANUP -eq 1 ]; then
        cleanup "$TMP_DIR"
    fi

    # Present follow-up options
    echo "[Next] Run openlibrary deploy (~12m00 as of 2024-12-09):"
    echo "time SERVER_SUFFIX='$SERVER_SUFFIX' ./scripts/deployment/deploy.sh openlibrary"
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

tag_deploy() {
    OL_REPO="$1"
    # Check if tag does NOT exist
    if ! git -C "$OL_REPO" rev-parse "$DEPLOY_TAG" >/dev/null 2>&1; then
        echo "[Info] Tagging deploy as $DEPLOY_TAG"
        git -C "$OL_REPO" tag "$DEPLOY_TAG"
        git -C "$OL_REPO" push git@github.com:internetarchive/openlibrary.git "$DEPLOY_TAG"
    else
        echo "[Info] Tag '$DEPLOY_TAG' already exists. Skipping creation."
    fi

    # Always update and push the 'production' tag
    git -C "$OL_REPO" tag -f production
    git -C "$OL_REPO" push -f git@github.com:internetarchive/openlibrary.git production
}

check_olbase_image_up_to_date() {
    echo "[Now] Checking if Docker image is up-to-date"

    # Get latest commit timestamp from GitHub API
    GITHUB_COMMIT_API="https://api.github.com/repos/internetarchive/openlibrary/commits/master"
    GIT_LAST_UPDATED=$(curl -s "$GITHUB_COMMIT_API" | jq -r '.commit.committer.date')
    echo "Latest Git commit: $GIT_LAST_UPDATED"

    # Get latest Docker image timestamp from Docker Hub
    IMAGE_META=$(curl -s https://hub.docker.com/v2/repositories/openlibrary/olbase/tags/latest)
    IMAGE_LAST_UPDATED=$(echo "$IMAGE_META" | jq -r '.last_updated')
    echo "Latest Docker image: $IMAGE_LAST_UPDATED"

    # Convert to timestamps
    GIT_LAST_UPDATED_TS=$(date_to_timestamp "$GIT_LAST_UPDATED")
    IMAGE_LAST_UPDATED_TS=$(date_to_timestamp "$IMAGE_LAST_UPDATED")

    if [ "$GIT_LAST_UPDATED_TS" -gt "$IMAGE_LAST_UPDATED_TS" ]; then
        echo "✗ Docker image is NOT up-to-date."
        echo -e "[Now] Manage docker image build status at: https://github.com/internetarchive/openlibrary/actions/workflows/olbase.yaml"
        return 1
    else
        echo "✓ Docker image is up-to-date."
        return 0
    fi
}

deploy_openlibrary() {
    echo "[Now] Deploying openlibrary"
    TMP_DIR=$(mktemp -d)

    cd $TMP_DIR
    echo -ne "Cloning openlibrary repo ... "
    git clone --depth=1 "https://github.com/internetarchive/openlibrary.git" openlibrary 2> /dev/null
    GIT_SHA=$(git -C openlibrary rev-parse HEAD | cut -c -7)
    echo "✔ (SHA: $GIT_SHA)"
    echo ""

    if ! check_olbase_image_up_to_date; then
       cleanup $TMP_DIR
       exit 1
    fi

    check_server_access
    check_crons

    echo "Checking for changes in the openlibrary repo on the servers..."
    for SERVER in $SERVERS; do
        check_for_local_changes $SERVER "/opt/openlibrary"
    done
    echo -e "No changes found in the openlibrary repo on the servers.\n"

    mkdir -p openlibrary_new
    cp -r openlibrary/compose*.yaml openlibrary_new
    cp -r openlibrary/docker openlibrary_new
    cp -r openlibrary/scripts openlibrary_new
    cp -r openlibrary/conf openlibrary_new
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

    if ! prune_docker image; then
        cleanup "$TMP_DIR"
        exit 1
    fi

    echo "Pull the latest docker images..."

    for SERVER_NAME in $SERVER_NAMES; do
        deploy_images "$SERVER_NAME"
    done

    echo -n "Waiting for servers ... "
    wait
    echo "✓"

    tag_deploy openlibrary

    echo "Finished production deployment at $(date)"
    echo "To reboot the servers, please run scripts/deployments/restart_all_servers.sh"

    cleanup $TMP_DIR

    echo "[Info] Skipping booklending utils; see \`deploy.sh utils\`"
    echo "[Next] Run review aka are_servers_in_sync.sh (~50s as of 2024-12-09):"
    echo "time SERVER_SUFFIX='$SERVER_SUFFIX' ./scripts/deployment/deploy.sh review"
}

deploy_images() {
    local SERVER_NAME=$1
    local SERVER="${SERVER_NAME}${SERVER_SUFFIX}"
    local COMPOSE_FILE="/opt/openlibrary/compose.yaml:/opt/openlibrary/compose.production.yaml"

    # Lazy-fetch OLBASE_DIGEST if not set
    if [ -z "$OLBASE_DIGEST" ]; then
        # We need to fetch by the exact image sha, since the registry mirror on the prod servers
        # has a cache which means fetching the `latest` image could be stale.
        # Assert latest docker image is up-to-date
        echo -n "   Fetching OLBASE_DIGEST ... "
        IMAGE_META=$(curl -s https://hub.docker.com/v2/repositories/openlibrary/olbase/tags/latest)
        OLBASE_DIGEST=$(echo "$IMAGE_META" | jq -r '.images[0].digest')
        echo "✓ ($OLBASE_DIGEST)"
    fi

    echo -n "   $SERVER_NAME ... "

    ssh -t "$SERVER" "
        set -e;
        docker pull openlibrary/olbase@${OLBASE_DIGEST}
        echo 'FROM openlibrary/olbase@${OLBASE_DIGEST}' | docker build --tag openlibrary/olbase:latest -f - .
        COMPOSE_FILE='${COMPOSE_FILE}' HOSTNAME=\$HOSTNAME docker compose --profile ${SERVER_NAME} pull
        source /opt/olsystem/bin/build_env.sh;
        COMPOSE_FILE='${COMPOSE_FILE}' HOSTNAME=\$HOSTNAME docker compose --profile ${SERVER_NAME} build
    " &> /dev/null &

    echo "(started in background)"
}


check_servers_in_sync() {
    echo "[Now] Ensuring git repo & docker images in sync across servers (~50s as of 2024-12-09):"
    time SERVER_SUFFIX="$SERVER_SUFFIX" "$SCRIPT_DIR/are_servers_in_sync.sh"
    echo "[Next] Run restart on all servers (~3m as of 2024-12-09):"
    echo "time SERVER_SUFFIX='$SERVER_SUFFIX' ./scripts/deployment/deploy.sh rebuild"
}

check_server_storage() {
    echo "Checking server storage space..."
    for SERVER in $SERVERS; do
        echo -n "   $SERVER ... "
        # Get available space (in bytes) for each relevant mount point
        AVAILABLE_SIZES=$(ssh $SERVER "sudo df -B1 | grep -E ' /[12]?$' | awk '{print \$4}'")
        for SIZE in $AVAILABLE_SIZES; do
            if [ "$SIZE" -lt 2147483648 ]; then
                echo "✗ (Less than 2GB free!)"
                ssh $SERVER "sudo df -h | grep -E ' /[12]?$'"
                return 1
            fi
        done
        echo "✓"
    done
    return 0
}

prune_docker () {
    echo "[Now] Prune docker images/cache..."

    PRUNE_CMD=""
    for arg in "$@"; do
        if [[ "$arg" == "image" ]]; then
            PRUNE_CMD+="docker image prune -f;"
        elif [[ "$arg" == "builder" ]]; then
            read -p "[Warning] Docker on servers MUST NOT be restarted while 'prune builder' running. Continue? [N/y]..." answer
            answer=${answer:-N}
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                PRUNE_CMD+="docker builder prune -f;"
            else
                echo "Abandoning prune"
                exit 1
            fi
        fi
    done

    for SERVER in $SERVERS; do
        echo -n "   $SERVER ... "

        if [[ -z "$PRUNE_CMD" ]]; then
            echo "[Error] Docker prune ran without image or builder args"
            echo "deploy prune [image|builder]+"
            exit 1
        fi

        if OUTPUT=$(ssh $SERVER "$PRUNE_CMD" 2>&1); then
            echo "✓"
        else
            echo "⚠"
            echo "$OUTPUT"
            return 1
        fi
    done
    return 0
}

clone_booklending_utils() {
    :
    # parallel --quote ssh {1} "echo -e '\n\n{}'; if [ -d /opt/booklending_utils ]; then cd {2} && sudo git pull git@git.archive.org:jake/booklending_utils.git master; fi" ::: $SERVERS ::: /opt/booklending_utils
}

recreate_services() {
    echo "[Now] Rebuilding & restarting services, keep an eye on sentry/grafana (~3m as of 2024-12-09)"
    echo "- Sentry: https://sentry.archive.org/organizations/ia-ux/issues/?project=7&statsPeriod=1d"
    echo "- Grafana: https://grafana.us.archive.org/d/000000176/open-library-dev?orgId=1&refresh=1m&from=now-6h&to=now"
    time SERVER_SUFFIX="$SERVER_SUFFIX" "$SCRIPT_DIR/restart_servers.sh"
}

post_deploy() {
    LATEST_TAG_NAME=$(git tag --sort=-creatordate | head -n 1)
    echo "[Now] Generate release: https://github.com/internetarchive/openlibrary/releases/new?tag=$LATEST_TAG_NAME"
    read -p "Once announced, press Enter to continue..."

    echo "[Now] Deploy complete, announce in #openlibrary-g, #openlibrary, and #open-librarians-g:"
    echo "The Open Library weekly deploy is now complete. See changes here: https://github.com/internetarchive/openlibrary/releases/tag/$LATEST_TAG_NAME. Please let us know @here if anything seems broken or delightful!"
}

deploy_wizard() {
    # Pull openlibrary before continuing so we have latest deploy.sh
    read -p "[Now] Switching to main branch and pulling latest changes? [Y/n]..." answer
    answer=${answer:-Y}
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        git checkout master
        git pull https://github.com/internetarchive/openlibrary.git master
    fi
    echo ""

    # Announce the deploy
    echo "[Now] Announce deploy to #openlibrary-g, #openlibrary, and #open-librarians-g:"
    echo "@here, Open Library is in the process of deploying its weekly release. See what's changed: $RELEASE_DIFF_URL"
    read -p "Once announced, press Enter to continue..."
    echo ""

    if ! check_olbase_image_up_to_date; then
        read -p "Once you've clicked 'Run workflow', press Enter to continue..."
    fi
    echo ""

    # Deploy olsystem
    echo "[Next] Run olsystem deploy (~2m30 as of 2024-12-06):"
    echo "time SERVER_SUFFIX='$SERVER_SUFFIX' ./scripts/deployment/deploy.sh olsystem"
    read -p "[Now] Run olsystem deploy now? [Y/n]..." answer
    answer=${answer:-Y}
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        time deploy_olsystem
    fi
    echo ""

    until check_olbase_image_up_to_date; do
        read -p "Once built, press Enter to continue..."
    done
    echo ""

    read -p "[Info] Skipping clone_booklending_utils, run manually if needed. Press Enter to continue..." answer
    echo ""

    read -p "[Now] Run openlibrary deploy & audit now? [N/y]..." answer
    answer=${answer:-Y}
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        time deploy_openlibrary
        echo ""
        time check_servers_in_sync
        echo ""
    fi

    read -p "[Now] Restart services and finalize deploy now? [N/y]..." answer
    answer=${answer:-N}
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        time recreate_services
        echo ""
        time post_deploy
        echo ""
    fi
}


# See deployment documentation at https://github.com/internetarchive/olsystem/wiki/Deployments
if [ "$1" == "olsystem" ]; then
    deploy_olsystem
elif [ "$1" == "openlibrary" ]; then
    deploy_openlibrary
    if [ "$2" == "--review" ]; then
        check_servers_in_sync
    fi
elif [ "$1" == "images" ]; then
    deploy_images $2
    wait
elif [ "$1" == "review" ]; then
    check_servers_in_sync
elif [ "$1" == "rebuild" ]; then
    recreate_services
elif [ "$1" == "prune" ]; then
    if [ "$2" == "--all" ]; then
        prune_docker image builder
    else
        prune_docker image
    fi
elif [ "$1" == "check_server_storage" ]; then
    check_server_storage
elif [ "$1" == "" ]; then  # If this works to detect empty
    deploy_wizard
else
    echo "Usage: $0 [olsystem|openlibrary|review|prune|rebuild|images|check_server_storage]"
    echo "e.g: time SERVER_SUFFIX='.us.archive.org' ./scripts/deployment/deploy.sh [command]"
    exit 1
fi
