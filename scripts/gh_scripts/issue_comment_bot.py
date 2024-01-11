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
    """
    Fetches all GitHub issues that have been updated since the given date string and have at least one comment.

    GitHub results are paginated.  This functions appends each result to a list, and does so for all pages.
    To keep API calls to a minimum, we request the maximum number of results per request (100 per page, as of writing).

    Important: Updated issues need not have a recent comment. Update events include many other things, such as adding a
    label to an issue, or moving an issue to a milestone.  Issues returned by this function will require additional
    processing in order to determine if they have recent comments.
    """
    # Make initial query for updated issues:
    query = f'repo:internetarchive/openlibrary is:open is:issue comments:>0 updated:>{updated_since}'
    response = requests.get(
        'https://api.github.com/search/issues',
        params={
            'q': query,
            'per_page': 100,
        },
    )
    d = response.json()
    results = d['items']

    # Fetch additional updated issues, if any exist
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

def filter_issues(issues: list, since: datetime):
    """
    Returns list of issues that were not last responded to by staff.
    Requires fetching the most recent comments for the given issues.
    """
    results = []

    for i in issues:
        # Fetch comments using URL from previous GitHub search results
        comments_url = i.get('comments_url')
        resp = requests.get(
            comments_url,
            params={
                'per_page': 100
            }
        )

        # Ensure that we have the last page of comments
        links = resp.links
        last = links.get('last', {})
        last_url = last.get('url', '')

        if last_url:
            resp = requests.get(last_url)

        # Get last comment
        comments = resp.json()
        last_comment = comments[-1]

        # Determine if last comment meets our criteria for Slack notifications
        # First step: Ensure that the last comment was left after the given `since` datetime
        created = datetime.fromisoformat(last_comment['created_at'])
        # Removing timezone info to avoid TypeErrors, which occur when
        # comparing a timezone-aware datetime with a timezone-naive datetime
        created = created.replace(tzinfo=None)
        if created > since:
            # Next step: Determine if the last commenter is a staff member
            last_commenter = last_comment['user']['login']
            if last_commenter not in staff_usernames:
                results.append({
                    'comment_url': last_comment['html_url'],
                    'commenter': last_commenter,
                    'issue_title': i['title'],
                })

    return results

def publish_digest(issues: list[str], slack_channel: str, slack_token: str, hours_passed: int):
    """
    Creates a threaded Slack messaged containing a digest of recently commented GitHub issues.

    Parent Slack message will say how many comments were left, and the timeframe. Each reply
    will include a link to the comment, as well as addiitonal information.
    """
    # Create the parent message
    parent_thread_msg = f'At least {len(issues)} new comment(s) have been left by contributors in the past {hours_passed} hour(s)'

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
        # XXX : Add retry logic?
        sys.exit(errno.ECOMM)

    d = response.json()
    # Store timestamp, which, along with the channel, uniquely identifies the parent thread
    ts = d.get('ts')

    def comment_on_thread(message: str):
        """
        Posts the given message as a reply to the parent message.
        """
        response = requests.post(
            'https://slack.com/api/chat.postMessage',
            headers={
                'Authorization': f"Bearer {slack_token}",
                'Content-Type': 'application/json;  charset=utf-8',
            },
            json={
                'channel': slack_channel,
                'text': message,
                'thread_ts': ts,
            },
        )
        if response.status_code != 200:
            # XXX : Log this
            print(f'Failed to POST slack message\n  Status code: {response.status_code}\n  Message: {message}')
            # XXX : Retry logic?

    for i in issues:
        # Slack rate limit is roughly 1 request per second
        time.sleep(1)

        comment_url = i['comment_url']
        issue_title = i['issue_title']
        commenter = i['commenter']
        message = f'<{comment_url}|Latest comment for: *{issue_title}*>\n'
        message += f'Commenter: *{commenter}*'
        comment_on_thread(message)

def time_since(hours):
    """Returns datetime and string representations of the current time, minus the given hour"""
    now = datetime.now()
    # XXX : Add a minute or two to the delta (to avoid dropping issues)?
    since = now - timedelta(hours=hours)
    return since, since.strftime(f'%Y-%m-%dT%H:%M:%S')

def start_job(args: dict):
    """
    Starts the new comment digest job.
    """
    since, date_string = time_since(args.hours)
    issues = fetch_issues(date_string)
    filtered_issues = filter_issues(issues, since)

    if filtered_issues:
        publish_digest(filtered_issues, args.channel, args.slack_token, args.hours)
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
        # XXX : Setting the defaults both here in the `get` calls and the config file
        # is like wearing a belt with suspenders...
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
        '-s',
        '--slack-token',
        help='Slack auth token',
        type=str,
        default=defaults['slack_token'],
    )

    return parser

if __name__ == '__main__':
    # Process command-line arguments and starts the notification job
    parser = _get_parser()
    args = parser.parse_args()
    start_job(args)
