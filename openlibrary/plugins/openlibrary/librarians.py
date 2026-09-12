"""Librarian tool pages: the workbench and the review page a queued batch
links to. JSON lives in openlibrary/fastapi/librarians.py.
"""

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core.librarian_batches import LibrarianBatches


def _librarian():
    user = accounts.get_current_user()
    return user if (user and user.is_librarian_or_higher()) else None


class librarians_workbench(delegate.page):
    path = "/librarians/workbench"

    def GET(self):
        user = _librarian()
        if not user:
            return render_template("permission_denied", "/librarians/workbench", "Librarians only")
        return render_template(
            "librarians/page",
            "librarians/workbench.html.jinja",
            username=user.key.split("/")[-1],
            is_super=bool(user.is_super_librarian_or_higher()),
        )


class librarians_batch(delegate.page):
    path = r"/librarians/batch/(\d+)"

    def GET(self, batch_id):
        user = _librarian()
        if not user:
            return render_template("permission_denied", "/librarians/batch", "Librarians only")
        batch = LibrarianBatches.get(int(batch_id))
        if not batch:
            raise delegate.notfound()
        return render_template(
            "librarians/page",
            "librarians/batch.html.jinja",
            batch=batch,
            is_super=bool(user.is_super_librarian_or_higher()),
            username=user.key.split("/")[-1],
        )


def setup():
    pass
