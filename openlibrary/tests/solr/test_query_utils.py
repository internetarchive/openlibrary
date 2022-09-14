import pytest
from openlibrary.solr.query_utils import (
    EmptyTreeError,
    luqum_parser,
    luqum_remove_child,
    luqum_traverse,
)

REMOVE_TESTS = {
    'Complete match': ('title:foo', 'title:foo', ''),
    'Binary Op Left': ('title:foo OR bar:baz', 'bar:baz', 'title:foo'),
    'Binary Op Right': ('title:foo OR bar:baz', 'title:foo', 'bar:baz'),
    'Group': ('(title:foo)', 'title:foo', ''),
    'Unary': ('NOT title:foo', 'title:foo', ''),
}


@pytest.mark.parametrize(
    "query,to_rem,expected", REMOVE_TESTS.values(), ids=REMOVE_TESTS.keys()
)
def test_luqum_remove_child(query: str, to_rem: str, expected: str):
    def fn(query: str, remove: str) -> str:
        q_tree = luqum_parser(query)
        for node, parents in luqum_traverse(q_tree):
            if str(node).strip() == remove:
                try:
                    luqum_remove_child(node, parents)
                except EmptyTreeError:
                    return ''
        return str(q_tree).strip()

    assert fn(query, to_rem) == expected


def test_luqum_parser():
    def fn(query: str) -> str:
        return str(luqum_parser(query))

    assert fn('title:foo') == 'title:foo'
    assert fn('title:foo bar') == 'title:(foo bar)'
    assert fn('title:foo AND bar') == 'title:(foo AND bar)'
    assert fn('title:foo AND bar AND by:boo') == 'title:(foo AND bar) AND by:boo'
    assert (
        fn('title:foo AND bar AND by:boo blah blah')
        == 'title:(foo AND bar) AND by:(boo blah blah)'
    )
    assert (
        fn('title:foo AND bar AND NOT by:boo') == 'title:(foo AND bar) AND NOT by:boo'
    )
    assert (
        fn('title:(foo bar) AND NOT title:blue') == 'title:(foo bar) AND NOT title:blue'
    )
    assert fn('no fields here!') == 'no fields here!'
    # This is non-ideal
    assert fn('NOT title:foo bar') == 'NOT title:foo bar'
