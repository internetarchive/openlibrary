import asyncio
import logging

from solr_builder_main import main


def parse_args():
    """
    Parse commandline arguments
    :rtype: argparse.Namespace
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="TODO add docs",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("cmd", choices=['index', 'fetch-end'],
                        help="Whether to do the index or just fetch end of the chunk")

    parser.add_argument("job", default="works", choices=['works', 'orphans', 'authors'],
                        help="Type to index. Orphans gets orphaned editions."
                             "Note orphans has to be done in one go :/ (TODO)")

    # Config
    parser.add_argument("--postgres", default="postgres.ini", help="Db config file")
    parser.add_argument("--ol-config", default="../../conf/openlibrary.yml",
                        help="ol server config file")
    parser.add_argument("--ol", default="http://ol/", help="URL of openlibrary website")

    # Query
    parser.add_argument("--start-at", default=None,
                        help="Key (type-prefixed) to start from as opposed to offset;"
                             "WAY more efficient since offset has to walk through all"
                             "`offset` rows.")
    parser.add_argument("--offset", default=0, type=int,
                        help="Use --start-at if possible")
    parser.add_argument("--limit", default=1, type=int)
    parser.add_argument("--last-modified", default=None,
                        help="Only import docs modified after this date")

    # Logging
    parser.add_argument("-p", "--progress", default=None,
                        help="Where to store the progress (if specified)")
    parser.add_argument("-l", "--log-file", default=None,
                        help="Send log to file instead of stdout (default)")
    parser.add_argument("--log-level", default=logging.WARN,
                        choices=['DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'],
                        type=lambda s: getattr(logging, s))

    return parser.parse_args()


if __name__ == '__main__':
    import tracemalloc

    # Capture X stack frames for each allocation (default=1)
    # tracemalloc.start(25)
    # try:
    args = parse_args()
    asyncio.run(main(**args.__dict__))
    # finally:
    #     snapshot = tracemalloc.take_snapshot()
    #     top_stats = snapshot.statistics('traceback')
    #
    #     print("[ Top 25 ]")
    #     for stat in top_stats[:25]:
    #         print("%s memory blocks: %.1f KiB" % (stat.count, stat.size / 1024))
    #         for line in stat.traceback.format():
    #             print(line)
