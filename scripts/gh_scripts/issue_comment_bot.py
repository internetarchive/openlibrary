#!/usr/bin/env python
"""
Fetches Open Library GitHub issues that have been commented on 
within some amount of time, in hours.

Writes links to each issue to Slack channel #team-abc-plus
"""
import argparse
import errno
import sys
import time

from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path

import requests

config_file = 'config/bot.ini'

# XXX : Configure?
staff_usernames = ['scottbarnes', 'mekarpeles', 'jimchamp', 'cdrini']

def fetch_issues(updated_since: str):
    query = f'repo:internetarchive/openlibrary is:open is:issue comments:>1 updated:>{updated_since}'
    response = requests.get(
        'https://api.github.com/search/issues?per_page=100',
        params={
            'q': query,
        },
    )
    d = response.json()
    results = d['items']

    # Pagination
    def get_next_page(url: str):
        """Returns list of issues and optional url for next page"""
        resp = requests.get(url)
        # Get issues
        d = resp.json()
        issues = d['items']
        # Prepare url for next page
        next = resp.links.get('next', {})
        next_url = next.get('url', '')

        return issues, next_url

    links = response.links
    next = links.get('next', {})
    next_url = next.get('url', '')
    while next_url:
        # Make call with next link
        issues, next_url = get_next_page(next_url)
        results = results + issues

    return results

def filter_issues(issues: list, since_date: str):
    """
    Returns list of issues that were not last responded to by staff.
    Requires fetching the most recent comments for the given issues.
    """
    filtered_issues = []

    for i in issues:
        comments_url = i.get('comments_url')
        resp = requests.get(f'{comments_url}?since{since_date}Z')
        comments = resp.json()
        last_comment = comments[-1]
        last_commenter = last_comment['user']['login']

        if last_commenter not in staff_usernames:
            filtered_issues.append(i)

    return filtered_issues

def publish_digest(issues: list[str], slack_channel: str, slack_token: str):
    parent_thread_msg = f'There are {len(issues)} issue(s) awaiting response.  More details in this thread.'
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={
            'Authorization': f"Bearer {slack_token}",
            'Content-Type': 'application/json;  charset=utf-8',
        },
        json={
            'channel': slack_channel,
            'text': parent_thread_msg,
        },
    )

    if response.status_code != 200:
        # XXX : Log this
        print(f'Failed to send message to Slack.  Status code: {response.status_code}')
        # XXX : Add retry logic
        sys.exit(errno.ECOMM)

    d = response.json()
    # Store timestamp, which, along with the channel, uniquely identifies the parent thread
    ts = d.get('ts')

    def comment_on_thread(message: str):
        response = requests.post(
            'https://slack.com/api/chat.postMessage',
            headers={
                'Authorization': f"Bearer {slack_token}",
                'Content-Type': 'application/json;  charset=utf-8',
            },
            json={
                'channel': slack_channel,
                'text': message,
                'thread_ts': ts
            },
        )
        if response.status_code != 200:
            # XXX : Log this
            print(f'Failed to POST slack message\n  Status code: {response.status_code}\n  Message: {message}')
            # XXX : Retry logic?

    for issue in issues:
        # Slack rate limit is roughly 1 request per second
        time.sleep(1)

        issue_url = issue.get('html_url')
        issue_title = issue.get('title')
        message = f'<{issue_url}|*{issue_title}*>'
        comment_on_thread(message)

def create_date_string(hours):
    now = datetime.now()
    # XXX : Add a minute or two to the delta?
    since = now - timedelta(hours=hours)
    return since.strftime(f'%Y-%m-%dT%H:%M:%S')

def start_job(args: dict):
    """
    Starts the new comment digest job.
    """
    date_string = create_date_string(args.hours)
    issues = fetch_issues(date_string)
    filtered_issues = filter_issues(issues, date_string)
    if filtered_issues:
        publish_digest(filtered_issues, args.channel, args.token)
    # XXX : Log this
    print('Digest POSTed to Slack')

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
