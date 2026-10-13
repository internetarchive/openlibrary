import datetime

import pytest
import web

from openlibrary.core.db import get_db
from openlibrary.core.edits import CommunityEditsQueue

DDL = """
CREATE TABLE community_edits_queue (
    id integer primary key autoincrement,
    title text,
    submitter text not null,
    reviewer text default null,
    url text not null,
    mr_type int not null default 1,
    status int not null default 1,
    updated timestamp
);
"""

DECLINED, PENDING, MERGED = 0, 1, 2
WORK, AUTHOR = 1, 2


def row(submitter, reviewer, status, mr_type=WORK, updated="2024-01-01 00:00:00"):
    return {
        "title": "t",
        "submitter": submitter,
        "reviewer": reviewer,
        "url": f"/merge/{submitter}/{reviewer}/{status}/{mr_type}/{updated}",
        "mr_type": mr_type,
        "status": status,
        "updated": updated,
    }


ROWS = [
    row("alice", "rita", MERGED, WORK),
    row("alice", "rita", MERGED, AUTHOR),
    row("alice", "rita", DECLINED, WORK),
    row("bob", "rita", DECLINED, WORK),
    row("bob", "sam", MERGED, WORK),
    row("bob", None, PENDING),
    row("carol", "sam", PENDING),
    row("carol", "sam", MERGED, WORK, updated="2023-01-01 00:00:00"),
]


class TestCommunityEditsQueueStats:
    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        db = get_db()
        # test_db.py creates a smaller version of this table in the same database
        db.query("DROP TABLE IF EXISTS community_edits_queue")
        db.query(DDL)
        db.multiple_insert("community_edits_queue", ROWS)

    @classmethod
    def teardown_class(cls):
        get_db().query("DROP TABLE IF EXISTS community_edits_queue")

    def test_reviewer_counts(self):
        stats = {r["username"]: r for r in CommunityEditsQueue.get_stats("reviewer")}
        assert set(stats) == {"rita", "sam"}
        assert stats["rita"] == {
            "username": "rita",
            "total": 4,
            "merged": 2,
            "declined": 2,
            "author_requests": 1,
            "work_requests": 3,
            "merge_rate": 50.0,
        }
        assert stats["sam"]["total"] == 2
        assert stats["sam"]["merged"] == 2

    def test_pending_requests_are_not_counted(self):
        submitters = {r["username"]: r for r in CommunityEditsQueue.get_stats("submitter")}
        assert submitters["bob"]["total"] == 2
        assert submitters["carol"]["total"] == 1

    def test_submitter_merge_rate(self):
        submitters = {r["username"]: r for r in CommunityEditsQueue.get_stats("submitter")}
        assert submitters["alice"]["merge_rate"] == pytest.approx(66.666, abs=0.01)
        assert submitters["bob"]["merge_rate"] == 50.0

    def test_unassigned_requests_have_no_reviewer_row(self):
        assert None not in {r["username"] for r in CommunityEditsQueue.get_stats("reviewer")}

    def test_since_limits_to_recent_requests(self):
        since = datetime.date(2023, 6, 1)
        assert {r["username"] for r in CommunityEditsQueue.get_stats("submitter", since=since)} == {"alice", "bob"}
        assert CommunityEditsQueue.get_stats_count("submitter", since=since) == 2
        assert CommunityEditsQueue.get_stats_count("submitter") == 3

    def test_sort_and_order(self):
        by_total = [r["username"] for r in CommunityEditsQueue.get_stats("submitter", sort="total")]
        assert by_total == ["alice", "bob", "carol"]
        ascending = [r["username"] for r in CommunityEditsQueue.get_stats("submitter", sort="total", order="asc")]
        assert ascending == ["carol", "bob", "alice"]
        by_rate = [r["username"] for r in CommunityEditsQueue.get_stats("submitter", sort="rate")]
        assert by_rate[0] == "carol"

    def test_pagination(self):
        page_1 = CommunityEditsQueue.get_stats("submitter", limit=2, page=1)
        page_2 = CommunityEditsQueue.get_stats("submitter", limit=2, page=2)
        assert [r["username"] for r in page_1] == ["alice", "bob"]
        assert [r["username"] for r in page_2] == ["carol"]

    def test_unknown_role_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown stats role"):
            CommunityEditsQueue.get_stats("submitter; DROP TABLE x")
        with pytest.raises(ValueError, match="Unknown stats role"):
            CommunityEditsQueue.get_stats_count("status")
