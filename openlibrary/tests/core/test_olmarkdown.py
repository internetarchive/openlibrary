from openlibrary.core.olmarkdown import OLMarkdown

def test_olmarkdown():
    def md(text):
        return OLMarkdown(text).convert().strip()

    def p(html):
        # markdown always wraps the result in <p>.
        return "<p>%s\n</p>" % html

    assert md(u"**foo**") == p(u"<strong>foo</strong>")
    assert md(u"<b>foo</b>") == p(u'<b>foo</b>')
    assert md(u"https://openlibrary.org") == p(
            u'<a href="https://openlibrary.org" rel="nofollow">' +
                u'https://openlibrary.org' +
            u'</a>'
        )
    assert md(u"http://example.org") == p(
            u'<a href="http://example.org" rel="nofollow">' +
                u'http://example.org' +
            u'</a>'
        )

    # why extra spaces?
    assert md(u"a\nb") == p(u"a<br/>\n   b")
