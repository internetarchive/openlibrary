#!/usr/bin/env python3

# matches ip#'s from input, builds reverse table to unhide hidden ips
# use:
#  sudo tcpdump -n (dst port 80 or dst port 443) | ./mktable
# leave running .. reveal uses the table
# or netstat -n | ./mktable
#
# or
# sudo tcpdump -n dst port 80 and 'tcp[tcpflags] & tcp-syn != 0' | ./mktable
#
# Exit with control+c.

import dbm.ndbm
import hashlib
import os
import re
import struct
import sys
import time
import urllib.request
from typing import Final

SEED_PATH: Final = os.getenv("SEED_PATH", "")
if not SEED_PATH:
    print("Set $SEED_PATH to the URL of seed.txt")
    sys.exit(1)


class HashIP:
    """
    A class to hash IP addresses and store the real <-> obfuscated IP
    in a map file. Every day the map file changes.
    """

    def __init__(self, real_ip_prefix: str = "/var/tmp/fast/hide_ip_map_") -> None:
        self.real_ip_prefix = real_ip_prefix
        self.seed = b""
        self.yday = time.gmtime()[7]
        self.set_db()
        self.get_seed()

    def set_db(self) -> None:
        """Set the database."""
        # Catching file-locking errors makes testing easier.
        try:
            self.real_ips = dbm.ndbm.open(  # noqa: SIM115
                self.real_ip_prefix + str(self.yday), "c"
            )
            # the connection is handled manually to be able to resync. The context manager interfiere with this.
        except dbm.ndbm.error as e:
            if "Resource temporarily unavailable" in str(e):
                pass
            else:
                raise e

    def get_seed(self) -> None:
        """Get the day's seed."""
        try:
            with urllib.request.urlopen(SEED_PATH) as handle:
                content = handle.read()
        except Exception as e:  # noqa: BLE001
            print("Error retrieving seed:", e)
            sys.exit(1)

        _, seed = content.split(b"=")
        seed = seed.rstrip()
        self.seed = seed
        self.yday = time.gmtime()[7]

    def hide(self, ip: str) -> str:
        """
        Obfuscate an IP address. Each day, trigger a new seed change so
        the obfuscation map file is renamed.
        """
        # rekey?
        if self.yday != time.gmtime()[7]:
            self.get_seed()
        m = hashlib.md5()
        m.update(self.seed + ip.encode("utf-8"))
        bin_md5 = m.digest()
        return "0.%d.%d.%d" % struct.unpack_from("BBB", bin_md5)

    def process_input(self) -> None:
        """
        Read input from STDIN. When an IP is hidden, the original and
        obfuscated IPs are printed to STDOUT. If an IP is already
        obfuscated for the day, it is not printed to STDOUT.
        """
        count = 0
        line = sys.stdin.readline()
        try:
            while line:
                ips = re.findall(
                    r"[^\d]?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[^\d]?", line
                )
                for ip in ips:
                    if (hidden := self.hide(ip)) not in self.real_ips:  # type: ignore [operator]
                        count += 1
                        self.real_ips[hidden] = ip
                        # Every 10th IP, flush the DB to disk
                        if count % 10 == 0:
                            self.real_ips.close()
                            self.set_db()
                        print(ip, hidden)
                line = sys.stdin.readline()
        except KeyboardInterrupt:
            self.real_ips.close()


def main():
    hash_ip = HashIP()
    hash_ip.process_input()


if __name__ == "__main__":
    main()
