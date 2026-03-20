"""Tests for scripts/detect_missing_i18n.py"""

import sys
from unittest.mock import MagicMock

# detect_missing_i18n imports _init_path (for its side-effect)
sys.modules["_init_path"] = MagicMock()

from ..detect_missing_i18n import ErrorLevel, check_html


class TestCleanHTML:
    def test_empty_strings(self):
        assert check_html("") == []
        assert check_html("<p></p>") == []

    def test_internationalized_content(self):
        assert check_html("<p>$_('About this book:')</p>") == []
        assert check_html("<p>$:_('Would you like to <strong>return</strong>?')</p>") == []
        assert check_html('<p>$ungettext("%(count)d edition", "%(count)d editions", count)</p>') == []

    def test_non_translatable_content(self):
        assert check_html("<span>123</span>") == []
        assert check_html("<span>&times;</span>") == []
        assert check_html("<a href='https://example.com'>https://example.com</a>") == []
        assert check_html("<p>$variable</p>") == []
        assert check_html("<p>Lorem ipsum dolor sit amet</p>") == []
        assert check_html("<a>$get_language_name(page.key, get_lang() or 'en')</a>") == []
        assert check_html("<p>$:reformat_html(format(description), max_length=250)</p>") == []

    def test_attributes(self):
        assert check_html("<button title=\"$_('Submit')\"></button>") == []
        assert check_html("<input placeholder=\"$_('Name')\" />") == []
        assert check_html("<img alt='$_('Photo of author')'>") == []
        assert check_html("<img alt='✓'>") == []

    def test_html_comment_not_flagged(self):
        assert check_html("<!-- <p>Untranslated text</p> -->") == []
        assert check_html("$:_('Some content <i>HERE</i>')") == []
        assert check_html("$# Avoid newlines in the <a> tags") == []
        assert check_html("$ x = _('Some content <i>HERE</i>')") == []


class TestErrors:
    def test_untranslated_element_content(self):
        html = "<p>About this book:</p>"
        results = check_html(html)
        assert len(results) == 1
        errtype, _line_no, _pos, _match = results[0]
        assert errtype == ErrorLevel.ERR

    def test_untranslated_title_attribute(self):
        html = '<button title="Submit">$_("Click")</button>'
        results = check_html(html)
        assert len(results) == 1
        errtype, _line_no, _pos, _match = results[0]
        assert errtype == ErrorLevel.ERR

    def test_untranslated_alt_attribute(self):
        html = '<img src="photo.jpg" alt="Photo of author">'
        results = check_html(html)
        assert len(results) == 1
        errtype, _line_no, _pos, _match = results[0]
        assert errtype == ErrorLevel.ERR

    def test_multiple_errors_across_lines(self):
        html = """
            <p>First error</p>
            <p>Second error</p>
        """
        results = check_html(html)
        assert len(results) == 2
        assert all(r[0] == ErrorLevel.ERR for r in results)


class TestSkipDirectives:
    def test_inline_skip_directive(self):
        html = "<p>Untranslated text</p> $# detect-missing-i18n-skip-line"
        assert check_html(html) == []

    def test_previous_line_skip_directive(self):
        html = """
            $# detect-missing-i18n-skip-line
            <p>Untranslated text</p>
        """
        assert check_html(html) == []

    def test_skip_directive_does_not_affect_other_lines(self):
        html = """
            $# detect-missing-i18n-skip-line
            <p>Skipped</p>
            <p>Still flagged</p>
        """
        results = check_html(html)
        assert len(results) == 1
        assert results[0][1] == 4  # line 4

    def test_inline_skip_with_dollar_prefix(self):
        html = "<p>Untranslated text</p> $# detect-missing-i18n-skip-line"
        assert check_html(html) == []


class TestWarnCases:
    def test_warn_for_dollar_paren_element(self):
        # $(' after a tag open triggers a WARN (bypassed translation)
        html = "<p>$('Some text')"
        results = check_html(html)
        assert len(results) == 1
        assert results[0][0] == ErrorLevel.WARN

    def test_warn_for_dollar_paren_attribute(self):
        html = "<button title=\"$('Submit')\"></button>"
        results = check_html(html)
        assert len(results) == 1
        assert results[0][0] == ErrorLevel.WARN
