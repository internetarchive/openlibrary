#!/usr/bin/python

# Solr loading script. 

# To import a json dump:
#   ./solr-update.py --dump=dumpfile.json --solr=localhost:8012

# To import solr update log starting 3 days ago:
#   ../solr-update.py --rsync --days=3  --solr=localhost:8012

# You can use (for example) hours=3 or minutes=3 instead of days=3
# but (for now) you can't combine these.  

# When you use the rsync option, the process will keep running and
# listening to the update log until you kill the process.

import _init_path
from openlibrary import solr
