from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from infogami.utils.view import (
    public,  # noqa: F401 side effects may be needed
    safeint,  # noqa: F401 side effects may be needed
    render,
)


class bulk_search(delegate.page):
    path = "/search/bulk"

    def GET(self):
        return render['bulk_search/bulk_search']()


def setup():
    pass
