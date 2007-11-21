#!/usr/bin/python2.5
import sys, os
import web
import infogami
import infogami.config
import infogami.tdb.tdb

infogami.config.internalerror = web.emailerrors("ol.errors@gmail.com", web.debugerror)

infogami.config.db_parameters = dict(dbn='postgres', host='pharosdb', db=file('dbname').read().strip(), user='anand', pw='')
infogami.config.site = 'openlibrary.org'
infogami.config.encryption_key = eval(open('/etc/openlibrary.key').read())

infogami.config.cache_templates = True
infogami.config.db_printing = False
infogami.config.plugin_path += ['plugins']
infogami.config.plugins += ['openlibrary', 'search', 'pages', 'heartbeat', 'bookrev', 'upload', 'api', 'copyright']
infogami.config.solr_server_address = ('pharosdb.us.archive.org', 8993)

infogami.tdb.logger.set_logfile(open("tdb.log", "a"))

infogami.config.from_address = "noreply@demo.openlibrary.org"
infogami.config.smtp_server = "mail.archive.org"

if __name__ == "__main__":
    infogami.run()
