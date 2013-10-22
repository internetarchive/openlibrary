#! /usr/bin/env python
"""Script to update loans and waiting loans on regular intervals.

Tasks done:
* delete all waiting-loans that are expired
"""
import web
from openlibrary.core import waitinglist

def main():
    waitinglist.prune_expired_waitingloans()

if __name__ == "__main__":
    main()
    
