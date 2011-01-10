#!/usr/bin/env python

import logging
import _init_path
from openlibrary.core import minicron


def main(cronfile):
    logging.basicConfig(level=logging.DEBUG, format = "[%(levelname)s] : %(filename)s:%(lineno)d : %(message)s")
    cron = minicron.Minicron(cronfile)
    cron.run()
    
if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1]))
        
        
        
        
        
