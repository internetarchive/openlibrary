#!/usr/bin/env python3

"""
% `python3 get_web_error.py 2023-02-03/011556535629.html | lynx --stdin`

To see the contents of an Open Library user-reported like 2023-02-03/011556535629.html:
1. Copy this script into your user directory on any Open Library host.
2. Type the command above substituting in the error code you are looking for.

This script will ssh into hosts ol-web1 and ol-web2 and if that file is found in the
docker_container openlibrary_web_1, it will print its contents to stdout.

Type `yes` if ssh prompts you to add the hosts to your known_hosts file.

If lynx is not yet installed, please type `sudo apt-get install lynx` to install it.
"""

import subprocess
import sys

usage = f"""Usage: {sys.argv[0]} [filename] | lynx --stdin
filename is like 2023-02-03/000008077313.html"""


def get_web_error(
    filename: str,
    hosts=("ol-web1.us.archive.org", "ol-web2.us.archive.org"),
    docker_container: str = "openlibrary_web_1",
) -> str:
    """
    ssh into hosts ol-web1 and ol-web2 and if filename is found in the
    docker_container openlibrary_web_1 then return its contents.
    """
    file_path = f"/var/log/openlibrary/ol-errors/{filename}"
    for host in hosts:
        cmd = f"ssh -A -t {host} 'docker exec -i {docker_container} cat {file_path}'"
        try:
            if output := subprocess.check_output(cmd, shell=True, text=True):
                return output
        except subprocess.CalledProcessError as e:
            print(f"Error: {e!r}")
            raise (e)
    return f"Error: {file_path} was not found on {' or '.join(hosts)}."


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(get_web_error(sys.argv[1]))
    else:
        print(usage)
