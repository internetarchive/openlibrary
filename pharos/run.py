#!/usr/local/bin/python2.5
import sys
import web
import infogami
import infogami.tdb.tdb

#web.db._hasPooling = False
infogami.config.db_parameters = dict(dbn='postgres', host='pharosdb', db="pharos", user='anand', pw='')
infogami.config.site = 'openlibrary.org'
infogami.config.cache_templates = True
infogami.config.db_printing = False
infogami.config.plugin_path += ['plugins']
infogami.config.plugins += ['search', 'dump']
infogami.config.solr_server_address = ('pharosdb.us.archive.org', 8993)

infogami.tdb.logger.set_logfile(open("tdb.log", "a"))

@infogami.action
def migrateusers():
    import passwd
    passwd.migrate()

if __name__ == "__main__":
    infogami.run()
