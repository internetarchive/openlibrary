#!/bin/bash

ALL_SERVERS="ol-home0 ol-covers0 ol-web1 ol-web2 ol-www0 ol-solr0"
POLICY_SERVERS="ol-home0 ol-web1 ol-web2"
REPO_DIRS="/opt/olsystem /opt/openlibrary /opt/openlibrary/vendor/infogami"

print_git_sha() {
    SERVER=$1
    REPO_DIR=$2
    ssh $SERVER "
        cd $REPO_DIR;
        printf '%-15s' $SERVER;
        sudo git rev-parse HEAD
    "
}

export -f print_git_sha

check_repos() {
    SERVERS=$1
    REPO_DIRS=$2
    parallel --header --group "
        echo -e {dir}
        parallel --header --group print_git_sha {server} {dir} ::: server $SERVERS | sort
        echo ---
    " ::: dir $REPO_DIRS
}

check_docker_images() {
    SERVERS=$1
    parallel --group "
        ssh {} '
            printf '%-15s' {};
            hostname | docker image ls | grep olbase | grep latest
        ';
    " ::: $SERVERS | sort;
    echo "";
}

check_repos "$ALL_SERVERS" "$REPO_DIRS"
check_repos "$POLICY_SERVERS" "/opt/booklending_utils"
check_docker_images "$ALL_SERVERS"
