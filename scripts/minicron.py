#!/usr/bin/env python

import os
import sys
import datetime
import logging
import optparse
import _init_path
from openlibrary.core import minicron


def parse_options(args):
    parser = optparse.OptionParser(usage = "%prog [options] crontabfile")
    parser.add_option("-s", "--start-time", dest = "starttime",
                      default = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                      help = "Start time in the form YYYY-MM-DD hh:mm:ss (default is now)")
    parser.add_option("-d", "--debug", action = "store_true", dest = "debug", default = False,
                      help = "Enable debugging output")
    parser.add_option("-i", "--interval", dest="interval", type="int", default = 60,
                      help = "Number of seconds that are equivalent to a minute of the cron's internal timer. This is useful for scaling.(default is 60)")
    opts, args = parser.parse_args(args)
    if not args:
        raise parser.error("No crontab file specified")
    return opts, args


def main():
    opts, args = parse_options(sys.argv[1:])
    if opts.debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format = "[%(levelname)s] : %(filename)s:%(lineno)d : %(message)s")
    cron = minicron.Minicron(args[0], datetime.datetime.strptime(opts.starttime, "%Y-%m-%d %H:%M:%S"), opts.interval)
    try:
        cron.run()
    except KeyboardInterrupt:
        logging.info("User initiated shutdown")
        return 0
    return -1
    
    
if __name__ == "__main__":
    sys.exit(main())

        
        
        
        
        
