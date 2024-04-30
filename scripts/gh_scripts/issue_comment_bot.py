#!/usr/bin/env python
"""
Fetches Open Library GitHub issues that have been commented on
within some amount of time, in hours.

If called with a Slack token and channel, publishes a digest of
the issues that were identified to the given channel.

Adds the "Needs: Response" label to the issues in Github.
"""
import argparse
import errno
import os
import sys
import time

from datetime import datetime, timedelta
from typing import Any

import requests

# Maps lead label to GitHub username
lead_label_to_username = {
    'Lead: @mekarpeles': 'mekarpeles',
    'Lead: @cdrini': 'cdrini',
    'Lead: @scottbarnes': 'scottbarnes',
    'Lead: @seabelis': 'seabelis',
    'Lead: @jimchamp': 'jimchamp',
}

# Maps GitHub username to Slack ID
username_to_slack_id = {
    'mekarpeles': '<@mek>',
    'cdrini': '<@cdrini>',
    'scottbarnes': '<@U03MNR6T7FH>',
    'seabelis': '<@UAHQ39ACT>',
    'jimchamp': '<@U01ARTHG9EV>',
    'hornc': '<@U0EUS8DV0>',
}

github_headers = {
    'X-GitHub-Api-Version': '2022-11-28',
    'Accept': 'application/vnd.github+json',
}


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
    p: dict[str, str | int] = {
        'q': query,
        'per_page': 100,
    }
    response = requests.get(
        'https://api.github.com/search/issues', params=p, headers=github_headers
    )
    d = response.json()
    results = d['items']

    # Fetch additional updated issues, if any exist
    def get_next_page(url: str):
        """Returns list of issues and optional url for next page"""
        resp = requests.get(url, headers=github_headers)
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
            comments_url, params={'per_page': 100}, headers=github_headers
        )

        # Ensure that we have the last page of comments
        links = resp.links
        last = links.get('last', {})
        last_url = last.get('url', '')

        if last_url:
            resp = requests.get(last_url, headers=github_headers)

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
            if last_commenter not in username_to_slack_id:
                lead_label = find_lead_label(i.get('labels', []))
                results.append(
                    {
                        'number': i['number'],
                        'comment_url': last_comment['html_url'],
                        'commenter': last_commenter,
                        'issue_title': i['title'],
                        'lead_label': lead_label,
                    }
                )

    return results


def find_lead_label(labels: list[dict[str, Any]]) -> str:
    """
    Finds and returns the name of the first lead label found in the given list of GitHub labels.

    Returns an empty string if no lead label is found
    """
    result = ''
    for label in labels:
        if label['name'].startswith('Lead:'):
            result = label['name']
            break

    return result


def publish_digest(
    issues: list[dict[str, str]],
    slack_channel: str,
    slack_token: str,
    hours_passed: int,
):
    """
    Creates a threaded Slack messaged containing a digest of recently commented GitHub issues.

    Parent Slack message will say how many comments were left, and the timeframe. Each reply
    will include a link to the comment, as well as additional information.
    """
    # Create the parent message
    parent_thread_msg = (
        f'{len(issues)} new GitHub comment(s) since {hours_passed} hour(s) ago'
    )

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
            # XXX : Check "ok" field for errors
            # XXX : Log this
            print(
                f'Failed to POST slack message\n  Status code: {response.status_code}\n  Message: {message}'
            )
            # XXX : Retry logic?

    for i in issues:
        # Slack rate limit is roughly 1 request per second
        time.sleep(1)

        comment_url = i['comment_url']
        issue_title = i['issue_title']
        commenter = i['commenter']
        message = f'<{comment_url}|Latest comment for: *{issue_title}*>\n'

        username = lead_label_to_username.get(i['lead_label'], '')
        slack_id = username_to_slack_id.get(username, '')
        if slack_id:
            message += f'Lead: {slack_id}\n'
        elif i['lead_label']:
            message += f'{i["lead_label"]}\n'
        else:
            message += 'Lead: N/A\n'

        message += f'Commenter: *{commenter}*'
        comment_on_thread(message)


def time_since(hours):
    """Returns datetime and string representations of the current time, minus the given hour"""
    now = datetime.now()
    # XXX : Add a minute or two to the delta (to avoid dropping issues)?
    since = now - timedelta(hours=hours)
    return since, since.strftime('%Y-%m-%dT%H:%M:%S')


def add_label_to_issues(issues):
    for issue in issues:
        issue_labels_url = f"https://api.github.com/repos/internetarchive/openlibrary/issues/{issue['number']}/labels"
        response = requests.post(
            issue_labels_url,
            json={"labels": ["Needs: Response"]},
            headers=github_headers,
        )


def verbose_output(issues):
    """
    Prints detailed information about the given issues.
    """
    for issue in issues:
        print(f'Issue #{issue["number"]}:')
        print(f'\tTitle: {issue["issue_title"]}')
        print(f'\t{issue["lead_label"]}')
        print(f'\tCommenter: {issue["commenter"]}')
        print(f'\tComment URL: {issue["comment_url"]}')


def start_job(args: argparse.Namespace):
    """
    Starts the new comment digest job.
    """
    since, date_string = time_since(args.hours)
    issues = fetch_issues(date_string)

    filtered_issues = filter_issues(issues, since)
    if not args.no_labels:
        add_label_to_issues(filtered_issues)
        print('Issues labeled as "Needs: Response"')
    if args.slack_token and args.channel:
        publish_digest(filtered_issues, args.channel, args.slack_token, args.hours)
        print('Digest posted to Slack')
    if args.verbose:
        verbose_output(filtered_issues)


def _get_parser() -> argparse.ArgumentParser:
    """
    Creates and returns an ArgumentParser containing default values which were
    read from the config file.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'hours',
        help='Fetch issues that have been updated since this many hours ago',
        type=int,
    )
    parser.add_argument(
        '-c',
        '--channel',
        help="Issues will be published to this Slack channel",
        type=str,
    )
    parser.add_argument(
        '-t',
        '--slack-token',
        help='Slack auth token',
        type=str,
    )
    parser.add_argument(
        '--no-labels',
        help='Prevent the script from labeling the issues',
        action='store_true',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        help='Print detailed information about the issues that were found',
        action='store_true',
    )

    return parser


if __name__ == '__main__':
    # Process command-line arguments and starts the notification job
    parser = _get_parser()
    args = parser.parse_args()

    # If found, add token to GitHub request headers:
    github_token = os.environ.get('GITHUB_TOKEN', '')
    if github_token:
        github_headers['Authorization'] = f'Bearer {github_token}'
    start_job(args)
