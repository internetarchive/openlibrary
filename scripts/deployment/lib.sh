#!/bin/bash
# Helpers shared by the deployment scripts. Source this file; don't run it.

# Check that we can ssh into each host and run docker there. If docker says
# permission denied, add the user to the docker group; if sudo needs a password
# for that, print the command to run by hand. Returns 1 at the first host that
# isn't usable.
# usage: check_docker_access ol-web0.us.archive.org ol-web2.us.archive.org ...
check_docker_access() {
    local host output status
    for host in "$@"; do
        echo -n "   $host ... "
        status=0
        output=$(ssh -o ConnectTimeout=10 "$host" "docker ps -q > /dev/null" 2>&1) || status=$?
        if [ $status -eq 0 ]; then
            echo "✓"
            continue
        fi

        echo "✗"
        if [ $status -eq 255 ]; then
            echo "Could not ssh into $host:"
            echo "$output"
            return 1
        fi
        if [[ "$output" != *"permission denied"* ]]; then
            echo "docker isn't working on $host:"
            echo "$output"
            return 1
        fi

        # Group changes only apply to new logins, and each ssh call is a new login
        echo -n "     Not in the docker group, adding you ... "
        if ssh -o ConnectTimeout=10 "$host" 'sudo -n usermod -aG docker "$USER"' > /dev/null 2>&1 \
            && ssh -o ConnectTimeout=10 "$host" "docker ps -q > /dev/null" > /dev/null 2>&1; then
            echo "✓"
        else
            echo "✗"
            echo ""
            echo "Your account on $host isn't allowed to use docker. Add yourself to the"
            echo "docker group (sudo will ask for your password), then re-run:"
            echo ""
            echo "  ssh -t $host 'sudo usermod -aG docker \$USER'"
            return 1
        fi
    done
}
