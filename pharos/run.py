#!/usr/local/bin/python2.5
import sys
import web
import infogami

# Database parameters.
# ** EDIT THIS **
infogami.config.db_parameters = dict(dbn='postgres', db="pharos", user='anand', pw='')

infogami.config.site = 'openlibrary.org'
infogami.config.admin_password = "admin123"

infogami.config.cache_templates = True
infogami.config.db_printing = True

infogami.config.plugin_path += ['plugins']
infogami.config.plugins += ['openlibrary', "upload", "i18n", 'api', 'scod']

#infogami.config.plugins += ['search']
#infogami.config.solr_server_address = ('ia311530.us.archive.org', 8983)


web.config.infobase_logroot = "log"



#@@ other openlibrary plugins
#infogami.config.plugins += ['search']
#infogami.config.solr_server_address = ('pharosdb.us.archive.org', 8983)

def createsite():
    import web
    from infogami.infobase.infobase import Infobase
    web.config.db_parameters = infogami.config.db_parameters
    web.config.db_printing = True
    web.load()
    Infobase().create_site(infogami.config.site, infogami.config.admin_password)

if __name__ == "__main__":
    import sys
    if '--createsite' in sys.argv:
        createsite()
    else:
        infogami.run()

