"""
Script to mirror the Open Library production databse by replaying the logs.
"""

import infogami
import web
import time

web.config.db_parameters = dict(dbn='postgres', db="pharos_backup", user='anand', pw='')
#web.config.db_printing = True

from infogami.infobase.logreader import LogReader, RsyncLogFile, LogPlayback
from infogami.infobase.infobase import Infobase
import datetime

def playback():
    web.load()
    reader = LogReader(RsyncLogFile("wiki-beta::pharos/log", "log"))

    # skip the log till the latest entry in the database
    timestamp = web.query('SELECT last_modified FROM thing ORDER BY last_modified DESC LIMIT 1')[0].last_modified
    reader.skip_till(timestamp)

    playback = LogPlayback(Infobase())

    while True:
        for entry in reader:
            print reader.logfile.tell(), entry.timestamp
            playback.playback(entry)

        time.sleep(60)

if __name__ == '__main__':
    playback()

