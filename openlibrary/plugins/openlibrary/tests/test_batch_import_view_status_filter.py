import types
from unittest.mock import MagicMock, patch

import pytest

from openlibrary.plugins.openlibrary import code
from openlibrary.plugins.openlibrary.code import BatchImportView

ADMIN_KEY = "/people/admin"


def _view_batch(**params):
    batch = types.SimpleNamespace(id="5", submitter="owner", name="b", submit_time=None)
    db_mock = MagicMock()
    db_mock.select.side_effect = lambda table, **kw: [batch] if table == "import_batch" else []
    db_mock.query.return_value = [types.SimpleNamespace(count=0)]
    render = MagicMock(return_value="RENDERED")
    ctx = MagicMock()
    ctx.user = types.SimpleNamespace(key=ADMIN_KEY)
    with (
        patch.object(code, "db", db_mock),
        patch.object(code, "_get_members_of_group", lambda group: [ADMIN_KEY]),
        patch.object(code.delegate, "context", ctx),
        patch.object(code, "render_template", render),
        patch.object(code.web, "input", lambda **defaults: types.SimpleNamespace(**{**defaults, **params})),
    ):
        BatchImportView().GET("5")
    items_select = next(c for c in db_mock.select.call_args_list if c.args[0] == "import_item")
    count_query = db_mock.query.call_args_list[0]
    return types.SimpleNamespace(
        where=items_select.kwargs["where"],
        count_sql=count_query.args[0],
        queries=[c.args[0] for c in db_mock.query.call_args_list],
        rendered=render.call_args.kwargs,
    )


def test_status_filters_items_and_their_count():
    view = _view_batch(status="created")
    assert view.where == "batch_id=$batch_id AND status=$status"
    assert view.count_sql.endswith("WHERE batch_id=$batch_id AND status=$status")
    assert view.rendered["status"] == "created"


@pytest.mark.parametrize("status", ["", "bogus", "created' OR 1=1 --"])
def test_missing_or_unknown_status_shows_all_items(status):
    view = _view_batch(status=status)
    assert view.where == "batch_id=$batch_id"
    assert view.count_sql.endswith("WHERE batch_id=$batch_id")
    assert view.rendered["status"] is None


def test_error_filters_items_and_their_count():
    view = _view_batch(status="failed", error="item-is-serial")
    assert view.where == "batch_id=$batch_id AND status=$status AND error=$error"
    assert view.count_sql.endswith("WHERE batch_id=$batch_id AND status=$status AND error=$error")
    assert view.rendered["error"] == "item-is-serial"


def test_error_counts_cover_the_batch_failed_items():
    view = _view_batch()
    assert view.rendered["error"] is None
    assert any("GROUP BY error" in q and "status='failed'" in q for q in view.queries)
    assert "error_counts" in view.rendered
