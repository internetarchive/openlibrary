#!/usr/bin/env python
"""
CAUTION: This file should continue to support both Python 2 and Python 3 until
    issues internetarchive/openlibrary#4060 and internetarchive/openlibrary#4252
    are resolved.

Store count of unique IPs per day to infobase by parsing the nginx log files directly.

This file is currently (17 July 2018) run on production using cron.
"""
from datetime import datetime, timedelta
import os
import subprocess
import web
import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import infogami  # must be after _init_path
from openlibrary.config import load_config


def run_piped(cmds, stdin=None):
    """
    Run the commands piping one's output to the next's input.
    :param list[list[str]] cmds:
    :param file stdin: The stdin to supply the first command of the pipe
    :return: the stdout of the last command
    :rtype: file
    """
    prev_stdout = stdin
    for cmd in cmds:
        p = subprocess.Popen(cmd, stdin=prev_stdout, stdout=subprocess.PIPE)
        prev_stdout = p.stdout
    return prev_stdout


def store_data(data, day):
    """
    Store stats data about the provided date.
    :param dict data:
    :param datetime day:
    :return:
    """
    uid = day.strftime("counts-%Y-%m-%d")
    doc = web.ctx.site.store.get(uid) or {}
    doc.update(data)
    doc['type'] = 'admin-stats'
    web.ctx.site.store[uid] = doc


def count_unique_ips_for_day(day):
    """
    Get the number of unique visitors for the given day.
    Throws an IndexError if missing log for the given day.
    :param datetime day:
    :return: A dict of the form `{visitors: int}`
    :rtype: int
    """
    basedir = "/var/log/nginx/"

    # Cat the logs we'll be processing
    log_file = basedir + "access.log"
    zipped_log_file = log_file + day.strftime("-%Y%m%d.gz")

    if os.path.exists(zipped_log_file):
        cat_log_cmd = ["zcat", zipped_log_file]
    elif day > (datetime.today() - timedelta(days=5)):
        # if recent day, then they haven't been compressed yet
        cat_log_cmd = ["cat", log_file]
    else:
        raise IndexError("Cannot find log file for " + day.strftime("%Y-%m-%d"))

    out = run_piped(
        [
            cat_log_cmd,  # cat the server logs
            ["awk", '$2 == "openlibrary.org" { print $1 }'],  # get all the IPs
            ["sort", "-u"],  # get unique only
            ["wc", "-l"],  # count number of lines
        ]
    )

    return int(out.read())


def main(config, start, end):
    """
    Get the unique visitors per day between the 2 dates (inclusive) and store them
    in the infogami database. Ignores errors
    :param datetime start:
    :param datetime end:
    :return:
    """
    load_config(config)  # loads config for psql db under the hood
    infogami._setup()

    current = start
    while current <= end:
        try:
            count = count_unique_ips_for_day(current)
            store_data(dict(visitors=count), current)
        except IndexError as e:
            print(e.message)
        current += timedelta(days=1)


if __name__ == "__main__":
    from argparse import ArgumentParser
    import sys

    parser = ArgumentParser(
        description="Store count of unique IPs per day from the past K days (including today) in infobase."
    )
    parser.add_argument(
        'config', help="openlibrary.yml (e.g. olsystem/etc/openlibrary.yml)"
    )
    parser.add_argument('--days', type=int, default=1, help="how many days to go back")
    parser.add_argument(
        '--range',
        nargs=2,
        type=lambda d: datetime.strptime(d, "%Y-%m-%d"),
        help="alternatively, provide a range of dates to visit (like `--range 2018-06-25 2018-07-14`)",
    )
    args = parser.parse_args()

    if args.range:
        start, end = args.range
    else:
        end = datetime.today()
        start = end - timedelta(days=args.days)

    sys.exit(main(args.config, start, end))
