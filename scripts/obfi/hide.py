#!/usr/bin/env python3

# use: hide ip#
# prints hashed ip using current key

import hashlib
import os
import struct
import sys
import urllib.request
from typing import Final

SEED_PATH: Final = os.getenv("SEED_PATH", "")
if not SEED_PATH:
    print("Set $SEED_PATH to the URL of seed.txt")
    sys.exit(1)


class HashIP:
    """
    A class to hash IP an IP address based on a seed that changes once per day.
    """

    def __init__(self) -> None:
        self.seed = b""
        self.get_seed()

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

    def hide(self, ip: str) -> str:
        """Obfuscate the IP address"""
        m = hashlib.md5()
        m.update(self.seed + ip.encode("utf-8"))
        bin_md5 = m.digest()
        return "0.%d.%d.%d" % struct.unpack_from("BBB", bin_md5)


if __name__ == "__main__":
    hash_ip = HashIP()
    print(hash_ip.hide(sys.argv[1]))
