import pytest

from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.plugins.worksearch.schemes.editions import EditionSearchScheme
from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme
from openlibrary.plugins.worksearch.schemes.subjects import SubjectSearchScheme
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme


@pytest.mark.parametrize(
    ("scheme", "field", "expected"),
    [
        (WorkSearchScheme, "isbn", "isbn"),
        (WorkSearchScheme, "ISBN", "isbn"),
        (WorkSearchScheme, "author", "author_name"),
        (WorkSearchScheme, "AUTHOR", "author_name"),
        (WorkSearchScheme, "ID_GOODREADS", "id_goodreads"),
        (WorkSearchScheme, "Edition.ISBN", "edition.isbn"),
        (WorkSearchScheme, "foo", None),
        (EditionSearchScheme, "Publishers", "publisher"),
        (AuthorSearchScheme, "NAME", "name"),
        (AuthorSearchScheme, "isbn", None),
    ],
)
def test_canonical_field_name(scheme, field, expected):
    assert scheme(lang="en").canonical_field_name(field) == expected


@pytest.mark.parametrize(
    ("scheme", "query", "expected"),
    [
        (AuthorSearchScheme, "NAME:Twain", "name:Twain"),
        (AuthorSearchScheme, "Name:Mark Twain OR Top_Subjects:fiction", "name:(Mark Twain) OR top_subjects:fiction"),
        (SubjectSearchScheme, "Work_Count:[10 TO *]", "work_count:[10 TO *]"),
        (ListSearchScheme, "NAME:Fantasy", "name:Fantasy"),
        (EditionSearchScheme, "ISBN:0060935464", "isbn:0060935464"),
        (EditionSearchScheme, "ID_GOODREADS:123", "id_goodreads:123"),
        (EditionSearchScheme, "publishers:Harper", "publisher:Harper"),
        (EditionSearchScheme, "Publishers:Harper", "publisher:Harper"),
        (AuthorSearchScheme, "FOO:bar", "FOO\\:bar"),
    ],
)
def test_process_user_query_canonicalizes_fields(scheme, query, expected):
    assert scheme(lang="en").process_user_query(query) == expected
