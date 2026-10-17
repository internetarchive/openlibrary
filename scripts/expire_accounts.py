#!/usr/bin/env python3
import os
import sys
from datetime import UTC, datetime

import web

from openlibrary.setup import setup_for_script


def delete_old_links():
    for doc in web.ctx.site.store.values(type="account-link"):
        expiry_date = datetime.strptime(doc["expires_on"], "%Y-%m-%dT%H:%M:%S.%f")
        # Make expiry_date timezone-aware:
        expiry_date = expiry_date.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        key = doc["_key"]
        if expiry_date > now:
            print("Deleting link %s" % (key))
            del web.ctx.site.store[key]
        else:
            print("Retaining link %s" % (key))


def main():
    setup_for_script(os.environ["OL_CONFIG"])
    delete_old_links()
    return 0


if __name__ == "__main__":
    sys.exit(main())
