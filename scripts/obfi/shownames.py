#!/usr/bin/env python3

# this matches obscured IPs, resolves them if possible, and reveals the
# resolved host in []s
# use: cat /var/log/lighttpd/current-access.log | reveal | shownames

import re
import socket
import sys
from re import Match


def add_name(match: Match) -> str:
    ip = match.group(2)

    if ip[0:2] == "0.":
        name: str | None = None
    else:
        try:
            name = socket.gethostbyaddr(ip)[0]
        except:  # noqa E722
            name = None

    if name:
        return match.group(1) + name + "[" + ip + "]" + match.group(3)
    else:
        return match.group(1) + ip + match.group(3)


def run() -> None:
    line = sys.stdin.readline()
    ip_pattern = re.compile(r"([^\d]?)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})([^\d]?)")

    while line:
        named = ip_pattern.sub(add_name, line.rstrip())
        print(named)
        line = sys.stdin.readline()


if __name__ == "__main__":
    run()
