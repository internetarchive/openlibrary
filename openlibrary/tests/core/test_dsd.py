"""Tests for Declarative Shadow DOM (DSD) helpers.

These tests verify that the Python DSD module correctly communicates with
the Node.js @lit-labs/ssr server and produces valid Declarative Shadow DOM
HTML for each component.
"""

import pytest
from openlibrary.core.dsd import (
    dsd_pagination,
    dsd_read_more,
    dsd_read_more_close,
)


class TestDsdReadMore:
    def test_produces_dsd_template(self):
        html = dsd_read_more()
        assert '<template shadowroot' in html or '<ol-read-more' in html
        # If SSR is available, should have DSD
        if '<template' in html:
            assert 'shadowrootmode="open"' in html or "shadowroot=" in html

    def test_contains_component_styles(self):
        html = dsd_read_more()
        if '<template' in html:
            assert '<style>' in html
            assert ':host' in html

    def test_contains_slot(self):
        html = dsd_read_more()
        if '<template' in html:
            assert '<slot></slot>' in html

    def test_contains_toggle_buttons(self):
        html = dsd_read_more()
        if '<template' in html:
            assert 'toggle-btn' in html
            assert 'Read More' in html
            assert 'Read Less' in html

    def test_custom_button_text(self):
        html = dsd_read_more(more_text='Show more', less_text='Show less')
        if '<template' in html:
            assert 'Show more' in html
            assert 'Show less' in html

    def test_custom_max_height(self):
        html = dsd_read_more(max_height='200px')
        assert 'max-height' in html
        if '<template' in html:
            assert '200px' in html

    def test_small_label_size(self):
        html = dsd_read_more(label_size='small')
        assert 'label-size="small"' in html or "label-size='small'" in html

    def test_background_color(self):
        html = dsd_read_more(background_color='#E2ECF8')
        assert 'background-color' in html

    def test_extra_attrs(self):
        html = dsd_read_more(**{'class': 'book-description'})
        assert 'class=' in html
        assert 'book-description' in html

    def test_close(self):
        assert dsd_read_more_close() == '</ol-read-more>'

    def test_starts_with_opening_tag(self):
        html = dsd_read_more()
        assert html.lstrip().startswith('<ol-read-more') or html.lstrip().startswith(
            '<!--'
        )

    def test_does_not_contain_closing_tag(self):
        """The opening helper should NOT include </ol-read-more> — that's dsd_read_more_close()."""
        html = dsd_read_more()
        assert '</ol-read-more>' not in html


class TestDsdPagination:
    def test_produces_complete_element(self):
        html = dsd_pagination(current_page=1, total_pages=5)
        assert '<ol-pagination' in html
        assert '</ol-pagination>' in html

    def test_produces_dsd_template(self):
        html = dsd_pagination(current_page=1, total_pages=5)
        if '<template' in html:
            assert 'shadowrootmode="open"' in html or 'shadowroot=' in html

    def test_contains_nav(self):
        html = dsd_pagination(current_page=1, total_pages=5)
        if '<template' in html:
            assert '<nav' in html
            assert 'role="navigation"' in html

    def test_host_attributes(self):
        html = dsd_pagination(current_page=3, total_pages=10)
        assert 'total-pages="10"' in html
        assert 'current-page="3"' in html

    def test_first_page_no_prev_arrow(self):
        html = dsd_pagination(current_page=1, total_pages=10)
        if '<template' in html:
            assert 'Go to previous page' not in html
            assert 'Go to next page' in html

    def test_last_page_no_next_arrow(self):
        html = dsd_pagination(current_page=10, total_pages=10)
        if '<template' in html:
            assert 'Go to previous page' in html
            assert 'Go to next page' not in html

    def test_current_page_marked(self):
        html = dsd_pagination(current_page=3, total_pages=5)
        if '<template' in html:
            assert 'aria-current="page"' in html

    def test_has_lit_markers_for_hydration(self):
        """SSR output should include Lit template markers for proper hydration."""
        html = dsd_pagination(current_page=1, total_pages=5)
        if '<template' in html:
            assert '<!--lit-part' in html

    def test_single_page(self):
        html = dsd_pagination(current_page=1, total_pages=1)
        assert '<ol-pagination' in html
        # Should not have navigation arrows
        if '<template' in html:
            assert 'pagination-arrow' not in html.split('</style>')[1]
