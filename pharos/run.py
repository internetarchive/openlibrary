#!/usr/local/bin/python2.5
import sys
import web
import infogami
import infogami.tdb.tdb

#web.db._hasPooling = False
infogami.config.db_parameters = dict(dbn='postgres', host='pharosdb', db="pharos", user='anand', pw='')
infogami.config.site = 'openlibrary.org'
infogami.config.cache_templates = False
infogami.config.db_printing = True

infogami.tdb.logger.set_logfile(open("tdb.log", "a"))

if __name__ == "__main__":
    infogami.run()
