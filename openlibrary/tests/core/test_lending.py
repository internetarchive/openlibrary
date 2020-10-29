import pytest

from openlibrary.core import lending


class TestAddAvailability:
    def test_reads_ocaids(self, monkeypatch):
        def mock_get_availability_of_ocaids(ocaids):
            return {'foo': {'status': 'available'}}
        monkeypatch.setattr(lending, "get_availability_of_ocaids", mock_get_availability_of_ocaids)

        f = lending.add_availability
        assert f([{'ocaid': 'foo'}]) == [{'ocaid': 'foo', 'availability': {'status': 'available'}}]
        assert f([{'identifier': 'foo'}]) == [{'identifier': 'foo', 'availability': {'status': 'available'}}]
        assert f([{'ia': 'foo'}]) == [{'ia': 'foo', 'availability': {'status': 'available'}}]
        assert f([{'ia': ['foo']}]) == [{'ia': ['foo'], 'availability': {'status': 'available'}}]

    def test_handles_ocaid_none(self):
        f = lending.add_availability
        assert f([{}]) == [{}]

    def test_handles_availability_none(self, monkeypatch):
        def mock_get_availability_of_ocaids(ocaids):
            return {'foo': {'status': 'error'}}
        monkeypatch.setattr(lending, "get_availability_of_ocaids", mock_get_availability_of_ocaids)

        f = lending.add_availability
        r = f([{'ocaid': 'foo'}])
        print(r)
        assert r[0]['availability']['status'] == 'error'


def test_get_work_authors_and_related_subjects():
    """
    def get_work_authors_and_related_subjects(work_id):
    """
    """
    import web
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    actual = lending.get_work_authors_and_related_subjects(work_id="")
    # Exception: db_parameters are not specified in the configuration
    assert actual == "expected", actual
    actual = lending.get_work_authors_and_related_subjects(work_id="OL3498798W")
    assert actual == "expected", actual
    """


def test_cached_work_authors_and_subjects():
    """
    def cached_work_authors_and_subjects(work_id):
    """
    """
    import web
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    actual = lending.cached_work_authors_and_subjects(work_id="")
    # Exception: db_parameters are not specified in the configuration
    expected = {'authors': [], 'subject': []}
    assert actual == expected, actual
    actual = lending.cached_work_authors_and_subjects(work_id="OL3498798W")
    expected = {'authors': [], 'subject': []}
    assert actual == expected, actual
    """


compose_ia_url_params_expected = {
    None: (
        "http://archive.org/advancedsearch.php?q=openlibrary_work%3A%28%2A%29+AND+"
        "collection%3A%28inlibrary%29+AND+loans__status__status%3AAVAILABLE&fl%5B%5D="
        "identifier&fl%5B%5D=openlibrary_edition&fl%5B%5D=openlibrary_work&fl%5B%5D="
        "loans__status__status&rows=42&page=1&output=json&sort%5B%5D="
    ),
    (("subject", "testing"), ): (
        "http://archive.org/advancedsearch.php?q=openlibrary_work%3A%28%2A%29+AND+"
        "%28collection%3A%28inlibrary%29+OR+%28%21collection%3A%28printdisabled%29%29"
        "%29+AND+loans__status__status%3AAVAILABLE+AND+openlibrary_subject%3Atesting"
        "&fl%5B%5D=identifier&fl%5B%5D=openlibrary_edition&fl%5B%5D=openlibrary_work"
        "&fl%5B%5D=loans__status__status&rows=42&page=1&output=json&sort%5B%5D="
    ),
    (("work_id", ""), ): (
        "http://archive.org/advancedsearch.php?q=openlibrary_work%3A%28%2A%29+AND+"
        "collection%3A%28inlibrary%29+AND+loans__status__status%3AAVAILABLE&fl%5B%5D="
        "identifier&fl%5B%5D=openlibrary_edition&fl%5B%5D=openlibrary_work&fl%5B%5D="
        "loans__status__status&rows=42&page=1&output=json&sort%5B%5D="
    ),
    (("work_id", "OL3498798W"), ("_type", "other")): (
        "http://archive.org/advancedsearch.php?q=openlibrary_work%3A%28%2A%29+AND+"
        "collection%3A%28inlibrary%29+AND+loans__status__status%3AAVAILABLE&fl%5B%5D="
        "identifier&fl%5B%5D=openlibrary_edition&fl%5B%5D=openlibrary_work&fl%5B%5D="
        "loans__status__status&rows=42&page=1&output=json&sort%5B%5D="
    ),
}

# NOTE: lending.compose_ia_url(work_id="OL3498798W") defaults _type=None which raises
#       AttributeError: 'NoneType' object has no attribute 'lower


@pytest.mark.parametrize("params,expected", compose_ia_url_params_expected.items())
def test_compose_ia_url(params, expected):
    """
    def compose_ia_url(limit=None, page=1, subject=None, query=None, work_id=None,
                   _type=None, sorts=None, advanced=True):
    """
    params = params or []  # Deal with None, etc.
    actual = lending.compose_ia_url(**dict(params))
    assert actual == expected, actual


def test_BROKEN_compose_ia_url():
    """
    def compose_ia_url(limit=None, page=1, subject=None, query=None, work_id=None,
                   _type=None, sorts=None, advanced=True):
    """
    """
    import web
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    actual = lending.compose_ia_url(work_id="OL3498798W", _type="authors")
    # Exception: db_parameters are not specified in the configuration
    expected = ""
    assert actual == expected, actual

    actual = lending.compose_ia_url(work_id="OL3498798W", _type="subjects")
    expected = ""
    assert actual == expected, actual
    """
