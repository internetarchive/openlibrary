from openlibrary.plugins.inside.code import escape_q, search_inside

def test_escape_q():
    unchanged = ['test', 'ia:aaa', 'ia: aaa']
    for s in unchanged:
        assert escape_q(s) == s

def test_quote_snippet():
    quote_snippet = search_inside().quote_snippet
    assert quote_snippet('test') == 'test'
    assert quote_snippet('aaa {{{bbb ccc}}} ddd') == 'aaa <b>bbb ccc</b> ddd'
    assert quote_snippet('aaa {{{bbb\nccc}}} ddd') == 'aaa <b>bbb ccc</b> ddd'
    assert quote_snippet('aaa {{{bbb & ccc}}} ddd') == 'aaa <b>bbb &amp; ccc</b> ddd'
    assert quote_snippet('aaa {{{bbb}}} {{{ccc}}} ddd') == 'aaa <b>bbb</b> <b>ccc</b> ddd'
