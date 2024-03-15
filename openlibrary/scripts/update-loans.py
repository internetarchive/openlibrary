#!/usr/bin/env python
"""Script to update loans and waiting loans on regular intervals.

Tasks done:
* delete all waiting-loans that are expired
"""
import sys
import web
from openlibrary.core import waitinglist
from openlibrary.plugins.upstream import borrow

web.config.debug = False


def usage():
    print(
        "python scripts/openlibrary-server openlibrary.yml runscript scripts/update-loans.py [update-loans | update-waitinglists]"
    )


def main():
    try:
        cmd = sys.argv[1]
    except IndexError:
        cmd = "help"

    if cmd == "update-loans":
        borrow.update_all_loan_status()
    elif cmd == "update-waitinglists":
        waitinglist.prune_expired_waitingloans()
        waitinglist.update_all_waitinglists()
    elif cmd == "update-waitinglist":
        waitinglist.update_waitinglist(sys.argv[2])
    else:
        usage()


if __name__ == "__main__":
    main()
