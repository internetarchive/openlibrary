"""Tests for scripts/detect_missing_i18n.py"""

import sys
from unittest.mock import MagicMock

# detect_missing_i18n imports _init_path (for its side-effect)
sys.modules["_init_path"] = MagicMock()

from ..detect_missing_i18n import Errtype, check_html


class TestCleanHTML:
    def test_empty_string(self):
        assert check_html("") == []

    def test_no_tags(self):
        assert check_html("<p>$_('About this book:')</p>") == []

    def test_properly_wrapped_text(self):
        html = '<p>$_("About this book:")</p>'
        assert check_html(html) == []

    def test_properly_wrapped_text_colon_variant(self):
        html = "<p>$:_('Would you like to <strong>return</strong>?')</p>"
        assert check_html(html) == []

    def test_ungettext_is_ok(self):
        html = '<p>$ungettext("%(count)d edition", "%(count)d editions", count)</p>'
        assert check_html(html) == []

    def test_only_punctuation_after_tag(self):
        # Just punctuation/numbers after the tag — should not be flagged
        assert check_html("<span>123</span>") == []

    def test_url_after_tag(self):
        assert check_html("<a href='https://example.com'>https://example.com</a>") == []

    def test_variable_after_tag(self):
        assert check_html("<p>$variable</p>") == []

    def test_lorem_after_tag(self):
        # This is a common placeholder text that shouldn't be flagged
        assert check_html("<p>Lorem ipsum dolor sit amet</p>") == []


class TestErrors:
    def test_untranslated_element_content(self):
        html = "<p>About this book:</p>"
        results = check_html(html)
        assert len(results) == 1
        errtype, _line_no, _pos, _match = results[0]
        assert errtype == Errtype.ERR

    def test_untranslated_title_attribute(self):
        html = '<button title="Submit">$_("Click")</button>'
        results = check_html(html)
        assert len(results) == 1
        errtype, _line_no, _pos, _match = results[0]
        assert errtype == Errtype.ERR

    def test_untranslated_alt_attribute(self):
        html = '<img src="photo.jpg" alt="Photo of author">'
        results = check_html(html)
        assert len(results) == 1
        errtype, _line_no, _pos, _match = results[0]
        assert errtype == Errtype.ERR

    def test_multiple_errors_across_lines(self):
        html = """
            <p>First error</p>
            <p>Second error</p>
        """
        results = check_html(html)
        assert len(results) == 2
        assert all(r[0] == Errtype.ERR for r in results)


class TestTranslatedAttributes:
    def test_translated_title_no_error(self):
        html = "<button title=\"$_('Submit')\"></button>"
        assert check_html(html) == []

    def test_translated_placeholder_no_error(self):
        html = "<input placeholder=\"$_('Enter your name')\" />"
        assert check_html(html) == []

    def test_translated_alt_no_error(self):
        html = "<img src='photo.jpg' alt=\"$_('Photo of author')\">"
        assert check_html(html) == []


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
        assert results[0][1] == 4  # line 4 is flagged

    def test_inline_skip_with_dollar_prefix(self):
        # The skip regex requires a leading $ before the comment marker
        html = "<p>Untranslated text</p> $# detect-missing-i18n-skip-line"
        assert check_html(html) == []


class TestCommentedOutLines:
    def test_html_comment_not_flagged(self):
        # The error is after <!--, so it should be skipped
        html = "<!-- <p>Untranslated text</p> -->"
        assert check_html(html) == []

    def test_dollar_colon_prefix_not_flagged(self):
        html = "<p>$:_('Some content')</p>"
        assert check_html(html) == []


class TestWarnCases:
    def test_warn_for_dollar_paren_element(self):
        # $(' after a tag open triggers a WARN (bypassed translation)
        html = "<p>$('Some text')"
        results = check_html(html)
        assert len(results) == 1
        assert results[0][0] == Errtype.WARN

    def test_warn_for_dollar_paren_attribute(self):
        html = "<button title=\"$('Submit')\"></button>"
        results = check_html(html)
        assert len(results) == 1
        assert results[0][0] == Errtype.WARN
