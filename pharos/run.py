#!/usr/bin/python2.5
import sys, os
import web
import infogami
import infogami.config
import infogami.tdb.tdb

#infogami.config.internalerror = web.emailerrors("ol.errors@gmail.com", web.debugerror)

infogami.config.db_parameters = dict(dbn='postgres', db='pharos', user='anand', pw='')
infogami.config.site = 'openlibrary.org'

infogami.config.cache_templates = True
infogami.config.db_printing = False
infogami.config.plugin_path += ['plugins']
infogami.config.plugins += ['openlibrary', 'pages', 'bookrev', 'upload', 'copyright']

infogami.config.from_address = "noreply@demo.openlibrary.org"
infogami.config.smtp_server = "mail.archive.org"

if __name__ == "__main__":
    infogami.run()
