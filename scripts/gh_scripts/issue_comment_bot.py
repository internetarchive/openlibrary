#!/usr/bin/env python
"""
Fetches Open Library GitHub issues that have been commented on 
within some amount of time, in hours.

Writes links to each issue to Slack channel #team-abc-plus
"""
import argparse
import errno
import sys

from configparser import ConfigParser
from pathlib import Path


config_file = 'config/bot.ini'

def start_job(args: dict):
    """
    Starts the new comment digest job.
    """
    pass


def _get_parser() -> argparse.ArgumentParser:
    """
    Creates and returns an ArgumentParser containing default values which were
    read from the config file.
    """
    def get_defaults():
        """
        Reads the config file and returns a dict containing the default
        values for this script's arguments.

        Location of config file is expected to be a nested within this file's parent
        directory.  The relative file location is stored as `config_file`.
        """
        this_dir = Path(__file__).parent.resolve()
        config_path = this_dir / Path(config_file)
        if not config_path.exists():
            # XXX : Log to file:
            print(f'{config_file} does not exist.')
            sys.exit(errno.ENOENT)

        config = ConfigParser()
        config.read(config_path)
        return {
            'slack_token': config['tokens'].get('slack_token', ''),
            'hours': config['issue_digest'].getint('default_hours', 1),
            'slack_channel': config['issue_digest'].get('slack_channel', '#team-abc-plus'),
        }

    defaults = get_defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--hours',
        metavar='N',
        help='Fetch issues that have been updated since N hours ago',
        type=int,
        default=defaults['hours'],
    )
    parser.add_argument(
        '-c',
        '--channel',
        help="Issues will be published to this Slack channel",
        type=str,
        default=defaults['slack_channel'],
    )
    parser.add_argument(
        '-t',
        '--token',
        help='Slack auth token',
        type=str,
        default=defaults['slack_token'],
    )

    return parser

if __name__ == '__main__':
    parser = _get_parser()
    args = parser.parse_args()
    start_job(args)
