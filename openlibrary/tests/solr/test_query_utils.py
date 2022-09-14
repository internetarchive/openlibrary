from openlibrary.solr.query_utils import luqum_parser


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
