import os
from datetime import datetime

import requests


def send_slack_message(message: str):
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={
            'Authorization': f"Bearer {os.environ.get('SLACK_TOKEN')}",
            'Content-Type': 'application/json;  charset=utf-8',
        },
        json={
            'channel': '#team-abc-plus',
            'text': message,
        },
    )
    if response.status_code != 200:
        print(f"Failed to send message to Slack. Status code: {response.status_code}")
    else:
        print("Message sent to Slack successfully!")
        print(response.content)


if __name__ == "__main__":
    GH_LOGIN_TO_SLACK = {
        'cdrini': '<@cdrini>',
        'jimchamp': '<@U01ARTHG9EV>',
        'mekarpeles': '<@mek>',
        'scottbarnes': '<@U03MNR6T7FH>',
    }
    LABEL_EMOJI = {
        'Priority: 0': '🚨 ',
        'Priority: 1': '❗️ ',
    }

    INCLUDE_AUTHORS = ['mekarpeles', 'cdrini', 'scottbarnes', 'jimchamp']
    EXCLUDE_LABELS = [
        'Needs: Submitter Input',
        'State: Blocked',
    ]
    query = 'repo:internetarchive/openlibrary is:open is:pr -is:draft'
    # apparently `author` acts like an OR in this API and only this API -_-
    included_authors = " ".join([f"author:{author}" for author in INCLUDE_AUTHORS])
    excluded_labels = " ".join([f'-label:"{label}"' for label in EXCLUDE_LABELS])
    query = f'{query} {included_authors} {excluded_labels}'

    prs = requests.get(
        "https://api.github.com/search/issues",
        params={
            "q": query,
        },
    ).json()["items"]

    message = f"{len(prs)} open staff PRs:\n\n"
    for pr in prs:
        pr_url = pr['html_url']
        pr_age_days = (
            datetime.now() - datetime.strptime(pr['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        ).days
        message += f"<{pr_url}|*#{pr['number']}* | {pr['title']}>\n"
        message += ' | '.join(
            [
                f"by {pr['user']['login']} {pr_age_days} days ago",
                f"Assigned: {GH_LOGIN_TO_SLACK[pr['assignee']['login']] if pr['assignee'] else '⚠️ None'}",
                f"{', '.join(LABEL_EMOJI.get(label['name'], '') + label['name'] for label in pr['labels'])}\n\n",
            ]
        )

    send_slack_message(message)
