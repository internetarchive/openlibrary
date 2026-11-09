"""Tests for scripts/gh_scripts/issue_comment_bot.py"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ..gh_scripts import issue_comment_bot as bot


@pytest.mark.parametrize(
    ("commenter", "expected"),
    [("Staffer", [1]), ("issuelead", [1]), ("otherlead", []), ("contributor", []), ("some-bot", [])],
)
def test_only_staff_or_issue_lead_reply_clears_needs_response(monkeypatch, commenter, expected):
    now = datetime.now().isoformat()
    comment = {"user": {"login": commenter}, "created_at": now, "html_url": ""}
    labels = [{"name": "Needs: Response"}, {"name": "Lead: @IssueLead"}]
    issue = {"number": 1, "title": "", "updated_at": now, "comments": 1, "comments_url": "", "labels": labels}
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    monkeypatch.setattr(bot.requests, "get", lambda *a, **k: MagicMock(status_code=200, links={}, json=lambda: [comment]))
    bots = [{"githubUsername": "some-bot", "triggersNeedsResponse": True}]
    _, lead_replied = bot.filter_issues([issue], 24, ["staffer"], bots)
    assert lead_replied == expected
