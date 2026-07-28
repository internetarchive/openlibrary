from openlibrary.core.olmarkdown import FencedCodePreprocessor, OLMarkdown


def test_olmarkdown():
    def md(text):
        return OLMarkdown(text).convert().strip()

    def p(html):
        # markdown always wraps the result in <p>.
        return "<p>%s\n</p>" % html

    assert md("**foo**") == p("<strong>foo</strong>")
    assert md("<b>foo</b>") == p("<b>foo</b>")
    assert md("https://openlibrary.org") == p('<a href="https://openlibrary.org" rel="nofollow">https://openlibrary.org</a>')
    assert md("http://example.org") == p('<a href="http://example.org" rel="nofollow">http://example.org</a>')

    # why extra spaces?
    assert md("a\nb") == p("a<br/>\n   b")


def test_olmarkdown_no_br_leak_into_reference_block():
    """Regression: a hard line break must not be glued onto a line that
    immediately precedes a markdown link-reference definition.

    LineBreaksPreprocessor runs before REFERENCE_PREPROCESSOR strips the
    ``[id]: url`` definitions, so a ``<br />`` appended to the line above a
    reference block gets orphaned inside it and leaks into the rendered page
    as literal markup. This was visible at the bottom of /help/faq/editing
    (internetarchive/openlibrary#13074), where a wrapped/malformed footnote
    block rendered ``...Tortilla<br /> [24]:`` etc.
    """

    def md(text):
        return OLMarkdown(text).convert().strip()

    # Text line immediately followed by a reference definition: no <br>.
    assert md("foo\n  [1]: https://example.com") == "<p>foo\n</p>"

    # A wrapped reference value (continuation line sitting between two
    # definitions, carrying the editor's "\" hard-break marker) must come out
    # clean: no leaked <br /> and no stray backslash.
    body = (
        "intro\n\n"
        "  [23]: https://openlibrary.org/works/OL23185W/Short_Novels\n"
        "(Cannery_Row_Of_Mice_and_Men_Tortilla\\\n"
        "  [24]: https://openlibrary.org/works/OL14876179W/Adventures\n"
    )
    rendered = md(body)
    assert "<br" not in rendered
    assert "\\" not in rendered

    # Sanity: an ordinary line break between two plain lines is untouched.
    assert md("a\nb") == "<p>a<br/>\n   b\n</p>"


def test_olmarkdown_commonmark_hard_break_does_not_leak_br():
    """Regression: a CommonMark hard break (trailing ``\\``) must render as a
    line break, not the literal text ``<br />``.

    The Tiptap WYSIWYG editor serializes hard breaks as ``\\`` + newline. With
    no handling, OLMarkdown appends its own ``<br />`` right after the
    backslash, the backslash escapes the ``<``, and readers see the literal
    string ``<br />`` (internetarchive/openlibrary#13074).
    """

    def md(text):
        return OLMarkdown(text).convert().strip()

    out = md("first line\\\nsecond line")
    assert "&lt;br" not in out  # no escaped/literal <br /> shown to the reader
    assert "\\" not in out  # the hard-break backslash is consumed
    assert out == "<p>first line<br/>\n   second line\n</p>"

    # A genuine escaped backslash (``\\``) is preserved, not swallowed.
    assert "\\" in md("a\\\\b\nc")


def test_fenced_code_preprocessor():
    pre = FencedCodePreprocessor()

    # Basic fenced block: lines between fences become 4-space indented;
    # the fence lines themselves are dropped.
    assert pre.run(["```", "code", "```"]) == ["    code"]

    # Language info string on the opening fence is dropped along with the fence.
    assert pre.run(["```python", "x = 1", "```"]) == ["    x = 1"]

    # Multi-line content is preserved verbatim, just indented.
    assert pre.run(["```", "a", "b", "c", "```"]) == ["    a", "    b", "    c"]

    # Pads a blank line *before* the block when the previous line is non-empty,
    # so the indented block reads as a fresh markdown block.
    assert pre.run(["before", "```", "code", "```"]) == ["before", "", "    code"]

    # No leading pad when the previous line is already blank.
    assert pre.run(["before", "", "```", "code", "```"]) == ["before", "", "    code"]

    # Pads a blank line *after* the block when the next line is non-empty.
    assert pre.run(["```", "code", "```", "after"]) == ["    code", "", "after"]

    # Multiple fenced blocks in one document are each rewritten independently.
    assert pre.run(["```", "a", "```", "between", "```", "b", "```"]) == ["    a", "", "between", "", "    b"]

    # Unterminated fence: the opening backticks pass through as a literal line
    # and the rest of the input is left untouched.
    assert pre.run(["```", "no closer", "still going"]) == [
        "```",
        "no closer",
        "still going",
    ]

    # Empty input is a no-op.
    assert pre.run([]) == []

    # Lines outside any fence are not modified.
    assert pre.run(["plain text"]) == ["plain text"]


def test_olmarkdown_fenced_code():
    def md(text):
        return OLMarkdown(text).convert().strip()

    # Basic fenced block renders as <pre><code>, not literal backticks + <br/>.
    assert md("```\ncode here\n```") == "<pre><code>code here\n</code></pre>"

    # Language info string is dropped; content survives.
    assert md("```python\nx = 1\nprint(x)\n```") == ("<pre><code>x = 1\nprint(x)\n</code></pre>")

    # Multi-line: newlines preserved, no <br/> injected inside the block.
    out = md("```\nline one\nline two\nline three\n```")
    assert "<pre><code>" in out
    assert "line one\nline two\nline three" in out
    assert "<br" not in out

    # Markdown/HTML inside a fence is rendered literally (HTML is escaped).
    out = md("```\n**not bold** <div>raw</div>\n# not heading\n```")
    assert "**not bold**" in out
    assert "&lt;div&gt;" in out
    assert "# not heading" in out
    assert "<strong>" not in out
    assert "<h1>" not in out

    # Surrounding paragraphs render independently of the fenced block.
    out = md("before\n\n```\ninside\n```\n\nafter")
    assert "<p>before" in out
    assert "<pre><code>inside\n</code></pre>" in out
    assert "<p>after" in out

    # Inline code with single backticks still works and is unaffected.
    assert md("some `inline` code") == "<p>some <code>inline</code> code\n</p>"

    # User repro from the WYSIWYG editor: heading + fence + inline + html block.
    body = "## Will it work\n\n```\nblock code here\n```\n\nThen some `inline code` here.\n\n<div>and finally an html block here</div>"
    out = md(body)
    assert "<h2>Will it work</h2>" in out
    assert "<pre><code>block code here\n</code></pre>" in out
    assert "<code>inline code</code>" in out
    assert "<div>and finally an html block here</div>" in out
    # The broken render-shape from the bug report must not appear.
    assert "`<br" not in out
    assert "`\n" not in out
