#!/usr/local/bin/python2.5
import sys
import web
import infogami
import infogami.tdb.tdb

# Database parameters.
# ** EDIT THIS **
infogami.config.db_parameters = dict(dbn='postgres', db="pharos", user='anand', pw='')

#@@ for openlibrary
#infogami.config.db_parameters = dict(dbn='postgres', host='pharosdb', db="pharos", user='anand', pw='')

infogami.config.site = 'openlibrary.org'
infogami.config.cache_templates = True
infogami.config.db_printing = True

infogami.config.plugins += ['dump']
infogami.config.plugin_path += ['plugins']

#@@ For openlibrary
#infogami.config.plugins += ['search']
#infogami.config.solr_server_address = ('pharosdb.us.archive.org', 8983)
#infogami.tdb.logger.set_logfile(open("tdb.log", "a"))

if __name__ == "__main__":
    infogami.run()
