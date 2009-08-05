#!/usr/bin/python

# Solr loading script. 

# Things that you might not expect:
#
# 1. When you run this script, it takes about 1 minute before any posts to
#    solr actually happen.
# 2. After you finish importing a json dump, the script sleeps for 5 minutes
#    before exiting
#
# There are implementation reasons for the above.  I should get around
# to fixing them, but in the normal case, importing a dump takes 12+
# hours, so a few more minutes doesn't make much difference.

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
