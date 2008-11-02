#!/usr/bin/env python

import infogami
import ol

## your db parameters
infogami.config.infobase_parameters = dict(type='local', dbn='postgres', db="openlibrary", user='anand', pw='')

infogami.config.db_printing = True

## site name 
infogami.config.site = 'openlibrary.org'
infogami.config.admin_password = "admin123"

infogami.config.login_cookie_name = "ol_session"

infogami.config.plugin_path += ['plugins']
infogami.config.plugins += ['openlibrary', "upload", "i18n", 'api', 'books']


if __name__ == "__main__":
    import sys
    if '--create' in sys.argv:
        ol.create()
    else:
        ol.run()
