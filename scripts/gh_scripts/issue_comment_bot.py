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
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import requests

github_headers = {
    'X-GitHub-Api-Version': '2022-11-28',
    'Accept': 'application/vnd.github+json',
}


# Custom Exceptions:
class AuthenticationError(Exception):
    # Raised when a required authentication token is missing from the environment.
    pass


class ConfigurationError(Exception):
    # Raised when reading the configuration goes wrong in some way.
    pass


def fetch_issues():
    """
    Fetches and returns all open issues and pull requests from the `internetarchive/openlibrary` repository.

    GitHub API results are paginated.  This functions appends each result to a list, and does so for all pages.
    To keep API calls to a minimum, we request the maximum number of results per request (100 per page, as of writing).

    Calls to fetch issues from Github are considered critical, and a failure of any such call will cause the script to
    fail fast.
    """
    # Make initial query for open issues:
    p = {'state': 'open', 'per_page': 100}
    response = requests.get(
        'https://api.github.com/repos/internetarchive/openlibrary/issues',
        params=p,
        headers=github_headers,
    )
    d = response.json()
    if response.status_code != 200:
        print('Initial request for issues has failed.')
        print(f'Message: {d.get("message", "")}')
        print(f'Documentation URL: {d.get("documentation_url", "")}')
        response.raise_for_status()

    results = d

    # Fetch additional updated issues, if any exist
    def get_next_page(url: str):
        """Returns list of issues and optional url for next page"""
        # Get issues
        resp = requests.get(url, headers=github_headers)
        d = resp.json()

        if resp.status_code != 200:
            print('Request for next page of issues has failed.')
            print(f'Message: {d.get("message", "")}')
            print(f'Documentation URL: {d.get("documentation_url", "")}')
            response.raise_for_status()

        issues = d

        # Prepare url for next page
        next = resp.links.get('next', {})
        next_url = next.get('url', '')

        return issues, next_url

    links = response.links
    next = links.get('next', {})
    next_url = next.get('url', '')
    while next_url:
        # Wait one second...
        time.sleep(1)
        # ...then, make call for more issues with next link
        issues, next_url = get_next_page(next_url)
        results = results + issues

    return results


def filter_issues(issues: list, hours: int, leads: list[dict[str, str]]):
    """
    Returns list of issues that have the following criteria:
    - Are issues, not pull requests
    - Issues have at least one comment
    - Issues have been last updated since the given number of hours
    - Latest comment is not from an issue lead

    Checking who left the last comment requires making up to two calls to
    GitHub's REST API.
    """

    def log_api_failure(_resp):
        print(f'Failed to fetch comments for issue #{i["number"]}')
        print(f'URL: {i["html_url"]}')
        _d = _resp.json()
        print(f'Message: {_d.get("message", "")}')
        print(f'Documentation URL: {_d.get("documentation_url", "")}')

    results = []

    since, date_string = time_since(hours)

    # Filter out as many issues as possible before making API calls for comments:
    prefiltered_issues = []
    for i in issues:
        updated = datetime.fromisoformat(i['updated_at'])
        updated = updated.replace(tzinfo=None)
        if updated < since:
            # Issues is stale
            continue

        if i.get('pull_request', {}):
            # Issue is actually a pull request
            continue

        if i['comments'] == 0:
            # Issue has no comments
            continue

        prefiltered_issues.append(i)

    print(f'{len(prefiltered_issues)} issues remain after initial filtering.')
    print('Filtering out issues with stale comments...')
    for i in prefiltered_issues:
        # Wait one second
        time.sleep(1)
        # Fetch comments using URL from previous GitHub search results
        comments_url = i.get('comments_url')

        resp = requests.get(comments_url, headers=github_headers)

        if resp.status_code != 200:
            log_api_failure(resp)
            # XXX : Somehow, notify Slack of error
            continue

        # Ensure that we have the last page of comments
        links = resp.links
        last = links.get('last', {})
        last_url = last.get('url', '')

        if last_url:
            resp = requests.get(last_url, headers=github_headers)
            if resp.status_code != 200:
                log_api_failure(resp)
                # XXX : Somehow, notify Slack of error
                continue

        # Get last comment
        comments = resp.json()
        if not comments:
            continue
        last_comment = comments[-1]

        # Determine if last comment meets our criteria for Slack notifications
        # First step: Ensure that the last comment was left after the given `since` datetime
        created = datetime.fromisoformat(last_comment['created_at'])
        # Removing timezone info to avoid TypeErrors, which occur when
        # comparing a timezone-aware datetime with a timezone-naive datetime
        created = created.replace(tzinfo=None)
        if created > since:
            # Next step: Determine if the last commenter is a lead
            last_commenter = last_comment['user']['login']
            if last_commenter not in [lead['githubUsername'] for lead in leads]:
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
    hours_passed: int,
    leads: list[dict[str, str]],
    all_issues_labeled: bool,
):
    """
    Creates a threaded Slack messaged containing a digest of recently commented GitHub issues.

    Parent Slack message will say how many comments were left, and the timeframe. Each reply
    will include a link to the comment, as well as additional information.
    """

    def post_message(payload: dict[str, str]):
        return requests.post(
            'https://slack.com/api/chat.postMessage',
            headers={
                'Authorization': f"Bearer {os.environ.get('SLACK_TOKEN', '')}",
                'Content-Type': 'application/json;  charset=utf-8',
            },
            json=payload,
        )

    # Create the parent message
    parent_thread_msg = (
        f'{len(issues)} new GitHub comment(s) since {hours_passed} hour(s) ago'
    )

    response = post_message(
        {
            'channel': slack_channel,
            'text': parent_thread_msg,
        }
    )

    if response.status_code != 200:
        print(f'Failed to send message to Slack.  Status code: {response.status_code}')
        sys.exit(errno.EPIPE)

    d = response.json()
    if not d.get('ok', True):
        print(f'Slack request not ok.  Error message: {d.get("error", "")}')

    # Store timestamp, which, along with the channel, uniquely identifies the parent thread
    ts = d.get('ts')

    for i in issues:
        # Slack rate limit is roughly 1 request per second
        time.sleep(1)

        comment_url = i['comment_url']
        issue_title = i['issue_title']
        commenter = i['commenter']
        message = f'<{comment_url}|Latest comment for: *{issue_title}*>\n'

        username = next(
            (
                lead['githubUsername']
                for lead in leads
                if lead['leadLabel'] == i['lead_label']
            ),
            '',
        )
        slack_id = username and next(
            (
                lead['slackId']  # type: ignore[syntax]
                for lead in leads
                if lead['leadLabel'] == f'Lead: @{username}'
            ),
            '',
        )
        if slack_id:
            message += f'Lead: {slack_id}\n'
        elif i['lead_label']:
            message += f'{i["lead_label"]}\n'
        else:
            message += 'Unknown lead\n'

        message += f'Commenter: *{commenter}*'
        r = post_message(
            {
                'channel': slack_channel,
                'text': message,
                'thread_ts': ts,
            }
        )
        if r.status_code != 200:
            print(f'Failed to send message to Slack.  Status code: {r.status_code}')
        else:
            d = r.json()
            if not d.get('ok', True):
                print(f'Slack request not ok.  Error message: {d.get("error", "")}')

    if not all_issues_labeled:
        r = post_message(
            {
                'channel': slack_channel,
                'text': (
                    'Warning: some issues were not labeled "Needs: Response". '
                    'See the <https://github.com/internetarchive/openlibrary/actions/workflows/new_comment_digest.yml|log files> for more information.'
                ),
            }
        )


def time_since(hours):
    """Returns datetime and string representations of the current time, minus the given hour"""
    now = datetime.now()
    # XXX : Add a minute or two to the delta (to avoid dropping issues)?
    since = now - timedelta(hours=hours)
    return since, since.strftime('%Y-%m-%dT%H:%M:%S')


def add_label_to_issues(issues) -> bool:
    all_issues_labeled = True
    for issue in issues:
        # GitHub recommends waiting at least one second between mutative requests
        time.sleep(1)

        issue_labels_url = f"https://api.github.com/repos/internetarchive/openlibrary/issues/{issue['number']}/labels"
        response = requests.post(
            issue_labels_url,
            json={"labels": ["Needs: Response"]},
            headers=github_headers,
        )

        if response.status_code != 200:
            all_issues_labeled = False
            print(
                f'Failed to label issue #{issue["number"]} --- status code: {response.status_code}'
            )
            print(issue_labels_url)

    return all_issues_labeled


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


def read_config(config_path):
    with open(config_path, encoding='utf-8') as f:
        return json.load(f)


def token_verification(slack_channel: str = ''):
    """
    Checks that the tokens required for this job to run are available in the environment.

    A GitHub token is always required.  A Slack token is required only if a `slack_channel` is specified.

    :param slack_channel: Channel to publish the digest. Publish step is skipped if this is an empty string.
    :raises AuthenticationError: When required token is missing from the environment.
    """
    if not os.environ.get('GITHUB_TOKEN', ''):
        raise AuthenticationError('Required GitHub token not found in environment.')
    if slack_channel and not os.environ.get('SLACK_TOKEN', ''):
        raise AuthenticationError(
            'Slack token must be included in environment if Slack channel is provided.'
        )


def start_job():
    """
    Starts the new comment digest job.
    """
    # Process command-line arguments and starts the notification job
    parser = _get_parser()
    args = parser.parse_args()

    print('Checking for required tokens...')
    token_verification(args.slack_channel)

    github_headers['Authorization'] = f"Bearer {os.environ.get('GITHUB_TOKEN', '')}"

    try:
        print('Reading configuration file...')
        config = read_config(args.config)
        leads = config.get('leads', [])
    except (OSError, json.JSONDecodeError):
        raise ConfigurationError(
            'An error occurred while parsing the configuration file.'
        )

    print('Fetching issues from GitHub...')
    issues = fetch_issues()
    print(f'{len(issues)} found')

    print('Filtering issues...')
    filtered_issues = filter_issues(issues, args.hours, leads)
    print(f'{len(filtered_issues)} remain after filtering.')

    all_issues_labeled = True
    if not args.no_labels:
        print('Labeling issues as "Needs: Response"...')
        all_issues_labeled = add_label_to_issues(filtered_issues)
        if not all_issues_labeled:
            print('Failed to label some issues')
    if args.slack_channel:
        print('Publishing digest to Slack...')
        publish_digest(
            filtered_issues, args.slack_channel, args.hours, leads, all_issues_labeled
        )
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
        '--config',
        help="Path to configuration file",
        type=str,
    )
    parser.add_argument(
        '-s',
        '--slack-channel',
        help="Issues will be published to this Slack channel. Publishing to Slack will be skipped if this argument is missing, or is an empty string",
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
    try:
        print('Starting job...')
        start_job()
        print('Job completed successfully.')
    except AuthenticationError as e:
        # If a required token is missing from the environment, fail fast
        print(e)
        sys.exit(10)
    except ConfigurationError as e:
        # If the configuration file cannot be read or unmarshalled, fail fast
        print(e)
        sys.exit(20)
    except requests.exceptions.HTTPError as e:
        # Fail fast if we fail to fetch issues from GitHub
        print(e)
        sys.exit(30)
