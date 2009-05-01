#!/usr/bin/env python

import infogami
import ol

## your db parameters
ol.config.db_parameters = dict(dbn='postgres', db="openlibrary", user='anand', pw='')
infogami.config.db_printing = True

# take off search plugin as it makes the program to fail when there are no solr servers 
infogami.config.plugins.remove('search')

if __name__ == "__main__":
    ol.run()
