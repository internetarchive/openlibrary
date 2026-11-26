import subprocess
import sys
from pathlib import Path

from openlibrary import book_providers
from openlibrary.plugins.upstream.models import Edition

REPO_ROOT = Path(__file__).resolve().parents[2]


class MockSite:
    def get(self, key):
        return None


def make_edition(**data) -> Edition:
    return Edition(MockSite(), "/books/OL1M", data={"key": "/books/OL1M", "type": {"key": "/type/edition"}, **data})


def test_an_edition_is_recognised():
    assert book_providers._is_edition(make_edition())


def test_a_solr_edition_dict_is_not_an_edition():
    assert not book_providers._is_edition({"key": "/books/OL1M", "cover_i": 123})


def test_get_cover_url_reads_an_editions_own_covers():
    url = book_providers.get_cover_url(make_edition(covers=[123]))

    assert url is not None
    assert url.endswith("/b/id/123-M.jpg")


def test_importing_book_providers_does_not_load_the_upstream_models():
    """The solr updater imports book_providers; the upstream models would pull in most of the web app."""
    code = "import sys, openlibrary.book_providers; print('openlibrary.plugins.upstream.models' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, check=True)

    assert result.stdout.strip().splitlines()[-1] == "False"
