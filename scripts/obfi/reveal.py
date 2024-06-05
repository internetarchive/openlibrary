#!/usr/bin/env python3

# this matches obscured ip's and reveals them in ()'s
# use: cat /var/log/lighttpd/current-access.log | reveal

import dbm.ndbm
import re
import sys
import time


class IPRevealer:
    """A class to reveal obscured IP addresses obscured by hide.py."""

    def __init__(self, real_ips, replace: bool):
        self.real_ips = real_ips
        self.replace = replace

    def make_real(self, match: re.Match) -> str:
        """Replace the obscured IP with the real IP or append it in parentheses."""
        hidden = match.group(2)
        if hidden in self.real_ips:
            if self.replace:
                return match.group(1) + self.real_ips[hidden].decode() + match.group(3)
            else:
                return (
                    match.group(1)
                    + hidden
                    + "("
                    + self.real_ips[hidden].decode()
                    + ")"
                    + match.group(3)
                )
        else:
            return match.group(1) + hidden + match.group(3)

    def run(self) -> None:
        """Read lines from STDIN and print any associated revealed IPs."""
        line = sys.stdin.readline()
        while line:
            revealed = re.sub(
                r"([^\d]?)(0\.\d{1,3}\.\d{1,3}\.\d{1,3})([^\d]?)",
                self.make_real,
                line.rstrip(),
            )
            print(revealed)
            sys.stdout.flush()
            line = sys.stdin.readline()


def get_real_ips_file_path() -> str:
    """Construct the real IPs file path."""
    # real_ips = dbm.open('/var/tmp/hide_ip_map_' + str(time.gmtime()[7]), 'r')
    return f"/var/tmp/fast/hide_ip_map_{time.gmtime()[7]!s}"


if __name__ == "__main__":
    with dbm.ndbm.open(get_real_ips_file_path(), "r") as real_ips:
        replace = len(sys.argv) > 1 and sys.argv[1] == "replace"

        ip_revealer = IPRevealer(real_ips, replace)
        ip_revealer.run()
