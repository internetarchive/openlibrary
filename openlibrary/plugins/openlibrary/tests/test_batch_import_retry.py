from datetime import datetime
from types import SimpleNamespace

import pytest
import web

from openlibrary.plugins.openlibrary import code


@pytest.mark.parametrize(("is_admin", "shows_retry"), [(True, True), (False, False)])
def test_batch_status_get_renders_retry_action(render_template, monkeypatch, is_admin, shows_retry):
    username = "admin" if is_admin else "patron"
    user = SimpleNamespace(
        key=f"/people/{username}",
        get_username=lambda: username,
        is_admin=lambda: is_admin,
    )
    monkeypatch.setattr(code.delegate.context, "user", user, raising=False)
    monkeypatch.setattr(code, "_get_members_of_group", lambda _: ["/people/admin"] if is_admin else [])
    monkeypatch.setattr(code.web, "input", lambda **_: web.storage(page=1, limit=10, sort="added_time asc"))
    monkeypatch.setattr(
        code.db,
        "select",
        lambda table, **_: (
            [web.storage(id=42, name="batch", submitter=username, submit_time=datetime(2026, 1, 1))]
            if table == "import_batch"
            else []
        ),
    )

    def query(statement, **_):
        if "GROUP BY status" in statement:
            return [web.storage(status="failed", count=1)]
        if "COUNT(*) AS count" in statement:
            return [web.storage(count=1)]
        return []

    monkeypatch.setattr(code.db, "query", query)
    monkeypatch.setitem(web.template.Template.globals, "changequery", lambda **_: "#")
    monkeypatch.setitem(web.template.Template.globals, "macros", web.storage(OlPagination=lambda *_: ""))

    html = str(code.BatchImportView.GET(None, "42"))

    assert ("Retry failed" in html) is shows_retry
