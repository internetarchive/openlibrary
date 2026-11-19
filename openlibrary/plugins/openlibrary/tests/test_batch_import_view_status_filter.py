import types
from unittest.mock import MagicMock, patch

import pytest

from openlibrary.plugins.openlibrary import code
from openlibrary.plugins.openlibrary.code import BatchImportView

ADMIN_KEY = "/people/admin"


def _view_batch(status):
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
        patch.object(
            code.web,
            "input",
            lambda **kw: types.SimpleNamespace(page="1", limit="10", sort="added_time asc", status=status),
        ),
    ):
        BatchImportView().GET("5")
    items_select = next(c for c in db_mock.select.call_args_list if c.args[0] == "import_item")
    count_query = db_mock.query.call_args_list[0]
    return items_select.kwargs["where"], count_query.args[0], render.call_args.kwargs["status"]


def test_status_filters_items_and_their_count():
    where, count_sql, status = _view_batch("created")
    assert where == "batch_id=$batch_id AND status=$status"
    assert count_sql.endswith("WHERE batch_id=$batch_id AND status=$status")
    assert status == "created"


@pytest.mark.parametrize("status", ["", "bogus", "created' OR 1=1 --"])
def test_missing_or_unknown_status_shows_all_items(status):
    where, count_sql, rendered_status = _view_batch(status)
    assert where == "batch_id=$batch_id"
    assert count_sql.endswith("WHERE batch_id=$batch_id")
    assert rendered_status is None
