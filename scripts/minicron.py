#!/usr/bin/env python

import _init_path
from openlibrary.core import minicron


def main(cronfile):
    cron = minicron.Minicron(cronfile)
    cron.run()
    
if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1]))
        
        
        
        
        
