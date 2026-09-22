"""Librarian tool pages: the workbench and its help page, an applied batch, and
the review page a queued request links to. JSON lives in openlibrary/fastapi/librarians.py.

The workbench is opt-in while it is vetted: these pages are for librarians in
/usergroup/workbench (and admins). The JSON endpoints enforce that only a
super-librarian applies, declines or resolves a request.
"""

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core import librarian_batches

DENIED = "Workbench testers only"


def _workbench_user():
    user = accounts.get_current_user()
    return user if (user and user.can_use_workbench()) else None


class librarians_workbench(delegate.page):
    path = "/librarians/workbench"

    def GET(self):
        user = _workbench_user()
        if not user:
            return render_template("permission_denied", "/librarians/workbench", DENIED)
        return render_template(
            "librarians/page",
            "librarians/workbench.html.jinja",
            username=user.key.split("/")[-1],
            is_super=bool(user.is_super_librarian_or_higher()),
        )


class librarians_workbench_help(delegate.page):
    path = "/librarians/workbench/help"

    def GET(self):
        if not _workbench_user():
            return render_template("permission_denied", "/librarians/workbench/help", DENIED)
        return render_template("librarians/page", "librarians/help.html.jinja")


def _record_page(kind, record_id, loader):
    user = _workbench_user()
    if not user:
        return render_template("permission_denied", f"/librarians/{kind}", DENIED)
    record = loader(int(record_id))
    if not record:
        raise delegate.notfound()
    return render_template(
        "librarians/page",
        "librarians/batch.html.jinja",
        batch=record,
        is_super=bool(user.is_super_librarian_or_higher()),
        username=user.key.split("/")[-1],
    )


class librarians_batch(delegate.page):
    path = r"/librarians/batch/(\d+)"

    def GET(self, batch_id):
        return _record_page("batch", batch_id, librarian_batches.get_batch)


class librarians_request(delegate.page):
    path = r"/librarians/request/(\d+)"

    def GET(self, request_id):
        return _record_page("request", request_id, librarian_batches.get_request)


def setup():
    pass
