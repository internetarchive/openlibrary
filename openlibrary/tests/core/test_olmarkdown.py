from openlibrary.core.olmarkdown import OLMarkdown


def md(text):
    """Helper function to convert markdown text to HTML."""
    return OLMarkdown(text).convert().strip()


def test_olmarkdown():
    def p(html):
        # markdown always wraps the result in <p>.
        return "<p>%s\n</p>" % html

    assert md("**foo**") == p("<strong>foo</strong>")
    assert md("<b>foo</b>") == p('<b>foo</b>')
    assert md("https://openlibrary.org") == p(
        '<a href="https://openlibrary.org" rel="nofollow">'
        'https://openlibrary.org'
        '</a>'
    )
    assert md("http://example.org") == p(
        '<a href="http://example.org" rel="nofollow">http://example.org</a>'
    )

    # why extra spaces?
    assert md("a\nb") == p("a<br/>\n   b")


def test_asterisk_safe_preprocessor():
    """Test that AsteriskSafePreprocessor fixes problematic asterisk patterns"""
    # **** (4 asterisks) should become heading #
    result = md("Some text\n\n**** Other \"Free\" guides\n\nMore text")
    assert "<h1>Other \"Free\" guides</h1>" in result
    assert "<strong/>" not in result  # Should not create self-closing strong tag

    # ** at line start (unclosed) should become * bullet point
    result = md("Text\n\n** Guide to Eastern Europe\n\nMore text")
    assert "<ul>" in result  # Should create unordered list
    assert "<li>" in result  # Should create list item

    # Valid **bold** should still work
    result = md("This is **bold** text")
    assert "<strong>bold</strong>" in result

    # Valid *italic* should still work
    result = md("This is *italic* text")
    assert "<em>italic</em>" in result

    # ***** (5 asterisks) should also become heading
    result = md("***** Five asterisks\nText")
    assert "<h1>Five asterisks</h1>" in result

    # ** followed by non-space should NOT be converted (e.g., **bold**)
    result = md("**bold** text")
    assert "<strong>bold</strong>" in result
    assert "<h1>bold</h1>" not in result

    # The full broken pattern from the issue
    result = md(
        "Text\n\n**** Other \"Free\" guides\n\n** Item 1\n** Item 2\n\nMore text"
    )
    assert "<h1>Other \"Free\" guides</h1>" in result
    assert "<ul>" in result
    assert "<em/>" not in result  # Should not have self-closing em tags

    # Ensure we don't break valid inline code
    result = md("Text with `inline code` and **bold**")
    assert "<code>inline code</code>" in result
    assert "<strong>bold</strong>" in result


def test_asterisk_separators():
    """Test that asterisk separator patterns are handled correctly."""
    # The actual problematic pattern from the issue
    result1 = md("Some text here\n\n* * *\n\nMore text")
    assert "<hr/>" in result1  # * * * should become a horizontal rule
    assert "<em/>" not in result1  # Should not have unclosed emphasis tags

    # Multiple isolated asterisks
    result4 = md("Text\n* *\nMore text")
    assert "<em>" not in result4 or "</em>" in result4

    # The actual separator pattern from the book description
    result9 = md("Description text\n\n* * *\n\nMore description")
    assert "<hr/>" in result9
    assert "More description" in result9


def test_unclosed_asterisks():
    """Test that unclosed asterisks don't leak across content."""
    # Single unclosed asterisk
    result2 = md("Text with * unclosed asterisk")
    assert "*" in result2 or "&#42;" in result2 or "<em>" not in result2

    # Asterisk at the end of a line
    result6 = md("Some text *\nNext line")
    lines = result6.split("\n")
    assert len([line for line in lines if "<em>" in line]) == len(
        [line for line in lines if "</em>" in line]
    )

    # Text ending with unclosed asterisk
    result12 = md("Some text with emphasis at the end *")
    assert "end" in result12

    # Unclosed asterisk in the middle of text
    result18 = md("Text with * unclosed and more text")
    assert "unclosed" in result18
    assert "more text" in result18

    # Asterisk at end without newline
    result19 = md("Text with unclosed * at end")
    assert "end" in result19


def test_asterisk_links():
    """Test that links with asterisks are handled correctly."""
    # Double asterisks around links (from issue comments)
    result3 = md("**[Some Work](/works/OL123W/)**")
    assert "<a href=" in result3  # Link should be created

    # Links wrapped in ** with more text
    result14 = md("**[Some Work](/works/OL123W/)** more text")
    assert "<a href=" in result14
    assert "Some Work" in result14


def test_asterisk_bullet_points():
    """Test that bullet point patterns with asterisks work correctly."""
    # Bullet points with * (the actual problematic pattern)
    result10 = md(
        "Some text\n\n* Guide to Eastern Europe\n* Guide to Southeast Asia\n\nMore text"
    )
    assert "<ul>" in result10  # Should create unordered list
    assert "<li>" in result10  # Should create list items
    assert "Guide" in result10
    assert "More text" in result10

    # Bullet points without proper spacing
    result11 = md("Text\n* Item 1\n* Item 2\nMore text")
    assert "Item 1" in result11
    assert "Item 2" in result11

    # ** at start of line converted to * bullet
    result16 = md("Text\n\n** Guide to Eastern Europe\n\nMore text")
    assert "<ul>" in result16  # Should create list
    assert "<li>" in result16  # Should create list item
    assert "Guide" in result16


def test_asterisk_headings():
    """Test that multiple asterisks are converted to headings."""
    # THE ACTUAL BUG - **** (4 asterisks) from broken version
    result15 = md("Some text\n\n**** Other \"Free\" guides\n\nMore text")
    assert "<h1>Other \"Free\" guides</h1>" in result15
    assert "<strong/>" not in result15  # Should not create self-closing strong tag
    assert "More text" in result15

    # Combined full broken pattern
    result17 = md(
        "Text\n\n**** Other \"Free\" guides\n\n** Item 1\n** Item 2\n\nMore text"
    )
    assert "<h1>Other \"Free\" guides</h1>" in result17
    assert "<ul>" in result17
    assert "Item 1" in result17
    assert "Item 2" in result17
    assert "More text" in result17
    assert "<em/>" not in result17


def test_actual_book_content():
    """Test real-world content from the problematic book description."""
    # Actual content from the problematic book description
    result5 = md(
        "Information doesn't want to be free: It wants to be expensive. In the network economy"
    )
    assert "network economy" in result5
    assert "<em>" not in result5 or "</em>" in result5

    # Unclosed emphasis across lines
    result7 = md("This is *italic text\nand this should be normal")
    assert "and this should be normal" in result7

    # Multiple asterisks in sequence
    result8 = md("Some text *** More text")
    assert "More text" in result8

    # Multiple asterisks at the end
    result13 = md("Text ending with ** ")
    assert "ending" in result13
