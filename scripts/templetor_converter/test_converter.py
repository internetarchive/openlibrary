"""Comprehensive test suite for the Templetor-to-Jinja2 converter.

Tests cover:
  - Basic expression conversion ($var → {{ var }})
  - Raw output ($:expr → {{ expr | safe }})
  - Explicit grouping ($(expr), ${expr})
  - Escaped dollar ($$)
  - Control flow ($for, $if, $elif, $else)
  - Variable assignment ($ var = expr)
  - $def with (macro definitions)
  - $code blocks
  - $def function definitions
  - Comments ($#)
  - i18n function calls ($_(), $:_())
  - $cond() → Jinja ternary
  - $ungettext() passthrough
  - Attribute access ($var.attr)
  - Complex expressions in conditionals
  - Full template conversions (5 incremental templates)
  - Edge cases and indentation sensitivity
"""

import os
import textwrap

import pytest

from scripts.templetor_converter.converter import (
    TempletorToJinjaConverter,
    convert_file,
    convert_text,
)

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def dedent(text: str) -> str:
    """Remove common leading whitespace from a multiline string."""
    return textwrap.dedent(text).lstrip("\n")


def assert_convert(input_text: str, expected: str, macro_name: str = "") -> None:
    """Assert that converting input_text produces expected output."""
    result = convert_text(dedent(input_text), macro_name=macro_name)
    assert result == dedent(expected), f"\n--- Expected ---\n{dedent(expected)}\n--- Got ---\n{result}\n---"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Expression conversion
# ═══════════════════════════════════════════════════════════════════════════


class TestExpressions:
    """Test basic Templetor expression conversion."""

    def test_bare_variable(self):
        assert_convert(
            "Hello $name!",
            "Hello {{ name }}!",
        )

    def test_bare_variable_at_start(self):
        assert_convert(
            "$name is here",
            "{{ name }} is here",
        )

    def test_dotted_attribute(self):
        assert_convert(
            "$user.name",
            "{{ user.name }}",
        )

    def test_deeply_dotted_attribute(self):
        assert_convert(
            "$page.type.key",
            "{{ page.type.key }}",
        )

    def test_multiple_variables(self):
        assert_convert(
            "$first and $second",
            "{{ first }} and {{ second }}",
        )

    def test_variable_in_html_attribute(self):
        assert_convert(
            '<a href="$link">text</a>',
            '<a href="{{ link }}">text</a>',
        )

    def test_raw_output(self):
        assert_convert(
            "$:content",
            "{{ content | safe }}",
        )

    def test_raw_output_function_call(self):
        assert_convert(
            "$:macros.Hello(name)",
            "{{ macros.Hello(name) | safe }}",
        )

    def test_raw_output_method_call(self):
        assert_convert(
            "$:form.render()",
            "{{ form.render() | safe }}",
        )

    def test_raw_output_parenthesized(self):
        assert_convert(
            "$:(compact_carousel(loans) or empty_carousel(loans))",
            "{{ (compact_carousel(loans) or empty_carousel(loans)) | safe }}",
        )

    def test_raw_output_render_template(self):
        assert_convert(
            '$:render_template("site/head", title=page.title)',
            '{{ render_template("site/head", title=page.title) | safe }}',
        )

    def test_raw_output_nested_calls(self):
        assert_convert(
            "$:macros.Foo(Bar(x), Baz(y))",
            "{{ macros.Foo(Bar(x), Baz(y)) | safe }}",
        )

    def test_raw_output_simple_identifier(self):
        assert_convert(
            "$:data_attr",
            "{{ data_attr | safe }}",
        )

    def test_raw_output_does_not_reprocess_i18n(self):
        """$:_ should not be double-processed by _convert_raw_expressions."""
        assert_convert(
            "$:_(" + '"' + "by %(name)s" + '"' + ", name=commify_list(render_items))",
            "{{ _(" + '"' + "by %(name)s" + '"' + ", name=commify_list(render_items)) | safe }}",
        )

    def test_raw_output_json_encode(self):
        assert_convert(
            "$:json_encode(data)",
            "{{ json_encode(data) | safe }}",
        )

    def test_explicit_paren_grouping(self):
        assert_convert(
            "Hello $(name)!",
            "Hello {{ name }}!",
        )

    def test_explicit_brace_grouping(self):
        assert_convert(
            "Hello ${name}!",
            "Hello {{ name }}!",
        )

    def test_escaped_dollar(self):
        assert_convert(
            "Price: $$10.00",
            "Price: $10.00",
        )

    def test_dollar_in_text(self):
        assert_convert(
            "The $ sign is special",
            "The $ sign is special",
        )

    def test_bare_function_call(self):
        assert_convert(
            "$subject_name_to_key(subject, prefix=prefix)",
            "{{ subject_name_to_key(subject, prefix=prefix) }}",
        )

    def test_bare_method_with_bracket(self):
        assert_convert(
            "$work.key.split('/')[-1]",
            "{{ work.key.split('/')[-1] }}",
        )

    def test_explicit_paren_nested(self):
        """$(expr) with nested parens like method call with args."""
        assert_convert(
            "$(doc['log']['shelf'].replace(' ', '-'))",
            "{{ doc['log']['shelf'].replace(' ', '-') }}",
        )

    def test_explicit_paren_simple_func(self):
        """$(func(arg)) with nested parens."""
        assert_convert(
            "$(urlquote(i))",
            "{{ urlquote(i) }}",
        )

    def test_raw_expression_with_bracket(self):
        """$:expr[0] should capture the bracket access."""
        assert_convert(
            "$:chapter_parts[0]",
            "{{ chapter_parts[0] | safe }}",
        )

    def test_for_with_colon_in_expression(self):
        """$for with [1:6] slice should not split on the colon."""
        assert_convert(
            "$for x, i in enumerate(doc.get('ia')[1:6]):\n    <p>$x</p>",
            "{% for x, i in enumerate(doc.get('ia')[1:6]) %}\n    <p>{{ x }}</p>\n{% endfor %}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. i18n function calls
# ═══════════════════════════════════════════════════════════════════════════


class TestI18n:
    """Test internationalization function call conversion."""

    def test_i18n_double_quotes(self):
        assert_convert(
            '$_("Hello World")',
            '{{ _("Hello World") }}',
        )

    def test_i18n_single_quotes(self):
        assert_convert(
            "$_('Hello World')",
            "{{ _('Hello World') }}",
        )

    def test_i18n_with_interpolation(self):
        assert_convert(
            '$_("%(name)s is here", name=user)',
            '{{ _("%(name)s is here", name=user) }}',
        )

    def test_i18n_raw_output(self):
        assert_convert(
            '$:_("Hello <b>World</b>")',
            '{{ _("Hello <b>World</b>") | safe }}',
        )

    def test_i18n_raw_single_quotes(self):
        assert_convert(
            "$:_('Hello World')",
            "{{ _('Hello World') | safe }}",
        )

    def test_i18n_with_escaped_quotes(self):
        assert_convert(
            "$_('It\\'s a test')",
            "{{ _('It\\'s a test') }}",
        )

    def test_i18n_in_html(self):
        assert_convert(
            '<h1>$_("Page Not Found")</h1>',
            '<h1>{{ _("Page Not Found") }}</h1>',
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Comments
# ═══════════════════════════════════════════════════════════════════════════


class TestComments:
    """Test comment conversion."""

    def test_simple_comment(self):
        assert_convert(
            "$# This is a comment",
            "{# This is a comment #}",
        )

    def test_comment_with_content(self):
        assert_convert(
            "$# Template for onboarding cards\n<p>content</p>",
            "{# Template for onboarding cards #}\n<p>content</p>",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Control flow
# ═══════════════════════════════════════════════════════════════════════════


class TestControlFlow:
    """Test $for, $if, $elif, $else conversion."""

    def test_simple_for(self):
        assert_convert(
            "$for i in range(3):\n    <p>$i</p>",
            "{% for i in range(3) %}\n    <p>{{ i }}</p>\n{% endfor %}",
        )

    def test_for_with_enumerate(self):
        assert_convert(
            "$for i, item in enumerate(items):\n    <p>$i: $item</p>",
            "{% for i, item in enumerate(items) %}\n    <p>{{ i }}: {{ item }}</p>\n{% endfor %}",
        )

    def test_simple_if(self):
        assert_convert(
            "$if name:\n    <p>Hello $name</p>",
            "{% if name %}\n    <p>Hello {{ name }}</p>\n{% endif %}",
        )

    def test_if_else(self):
        assert_convert(
            "$if show:\n    <p>Yes</p>\n$else:\n    <p>No</p>",
            "{% if show %}\n    <p>Yes</p>\n{% else %}\n    <p>No</p>\n{% endif %}",
        )

    def test_if_elif_else(self):
        assert_convert(
            "$if x == 1:\n    <p>One</p>\n$elif x == 2:\n    <p>Two</p>\n$else:\n    <p>Other</p>",
            "{% if x == 1 %}\n    <p>One</p>\n{% elif x == 2 %}\n    <p>Two</p>\n{% else %}\n    <p>Other</p>\n{% endif %}",
        )

    def test_nested_if(self):
        assert_convert(
            "$if a:\n    $if b:\n        <p>Both</p>",
            "{% if a %}\n    {% if b %}\n        <p>Both</p>\n    {% endif %}\n{% endif %}",
        )

    def test_for_with_if(self):
        assert_convert(
            "$for item in items:\n    $if item.active:\n        <p>$item.name</p>",
            "{% for item in items %}\n    {% if item.active %}\n        <p>{{ item.name }}</p>\n    {% endif %}\n{% endfor %}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Variable assignment
# ═══════════════════════════════════════════════════════════════════════════


class TestAssignment:
    """Test $ var = expr conversion."""

    def test_simple_assignment(self):
        assert_convert(
            "$ name = 'World'",
            "{% set name = 'World' %}",
        )

    def test_assignment_with_expression(self):
        assert_convert(
            "$ total = count + 1",
            "{% set total = count + 1 %}",
        )

    def test_assignment_with_method_call(self):
        assert_convert(
            "$ title = page.title",
            "{% set title = page.title %}",
        )

    def test_tuple_unpacking(self):
        assert_convert(
            "$ ed_olid, rest = chapter.split(' | ', 1)",
            "{% set ed_olid, rest = chapter.split(' | ', 1) %}",
        )

    def test_augmented_assignment(self):
        assert_convert(
            "$ x += 1",
            "{% set x = x + 1 %}",
        )

    def test_multiline_list_assignment(self):
        """Multi-line list assignments should be collected into a single {% set %}."""
        assert_convert(
            "$ allowed_videos = [\n$     'PJwBdVr_1LM'\n$ ]\n\n$if id in allowed_videos:\n    <p>yes</p>",
            "{% set allowed_videos = [ 'PJwBdVr_1LM' ] %}\n\n{% if id in allowed_videos %}\n    <p>yes</p>\n{% endif %}",
        )

    def test_multiline_strips_py_comments(self):
        """Python # comments in continuation lines should be stripped."""
        assert_convert(
            "$ allowed = [\n$     'item'  # inline comment\n$ ]",
            "{% set allowed = [ 'item' ] %}",
        )

    def test_dollar_space_method_call(self):
        """$ expr.method() should convert to {{ expr.method() }}."""
        assert_convert(
            "$ availability.update(get_availability(ocaid))",
            "{{ availability.update(get_availability(ocaid)) }}",
        )

    def test_dollar_space_simple_expr(self):
        """$ expr (with space) should convert like $expr."""
        assert_convert(
            "$ page.title",
            "{{ page.title }}",
        )

    def test_raw_expr_string_literal(self):
        """$:'string'.method() should be handled with string literal scanning."""
        assert_convert(
            "$:'; '.join(items)",
            "{{ '; '.join(items) | safe }}",
        )

    def test_raw_expr_underscore_method(self):
        """$:_.get(k, v) should NOT be skipped as i18n — it's a method access."""
        assert_convert(
            "$:_.get(namespace, key)",
            "{{ _.get(namespace, key) | safe }}",
        )

    def test_raw_i18n_still_works(self):
        """$:_(...) should still be handled as i18n raw output."""
        assert_convert(
            '$:_("Hello World")',
            '{{ _("Hello World") | safe }}',
        )

    def test_dict_literal_in_assignment(self):
        """Dict literals are valid Jinja2 — should produce {% set %}, not CODE."""
        assert_convert(
            "$ config = {'query': query, 'sort': sort}",
            "{% set config = {'query': query, 'sort': sort} %}",
        )

    def test_empty_dict_in_assignment(self):
        """Empty dict {} is valid Jinja2."""
        assert_convert(
            "$ x = {}",
            "{% set x = {} %}",
        )

    def test_percent_formatting_in_assignment(self):
        """% string formatting is valid Jinja2 (delegates to Python %)."""
        assert_convert(
            "$ x = '%.2f' % val",
            "{% set x = '%.2f' % val %}",
        )

    def test_percent_formatting_with_vars(self):
        """% formatting with multiple args."""
        assert_convert(
            "$ url = '/books/%s' % edition_key",
            "{% set url = '/books/%s' % edition_key %}",
        )

    def test_raw_expr_percent_formatting(self):
        """$:'%.2f' % expr should capture the full expression including %."""
        assert_convert(
            '$:"%.2f" % component[1]',
            '{{ "%.2f" % component[1] | safe }}',
        )

    def test_raw_expr_percent_formatting_parens(self):
        """$:'%.2f' % (expr) with parenthesized RHS."""
        assert_convert(
            '$:"%.2f" % (val * 100)',
            '{{ "%.2f" % (val * 100) | safe }}',
        )

    def test_hyphenated_macro_name(self):
        """Hyphens in macro names are replaced with underscores."""
        assert_convert(
            "$def with (name)\n<p>$name</p>",
            "{% macro forgot_ia(name) %}\n<p>{{ name }}</p>\n{% endmacro %}",
            macro_name="forgot-ia",
        )

    def test_type_hint_in_macro_args(self):
        """Type hints are stripped from macro arguments."""
        assert_convert(
            "$def with (page, edit_view: bool = False)\n<p>$page</p>",
            "{% macro Template(page, edit_view = False) %}\n<p>{{ page }}</p>\n{% endmacro %}",
        )

    def test_semicolon_in_assignment(self):
        """Trailing semicolons are stripped from assignments."""
        assert_convert(
            "$ name = 'hello';",
            "{% set name = 'hello' %}",
        )

    def test_i18n_with_comprehension_wraps_as_code(self):
        """$_() with comprehension inside wraps as CODE comment."""
        result = convert_text(
            "$_('in %(lang)s', lang=', '.join(l.name for l in items))",
            macro_name="Test",
        )
        assert "{# CODE:" in result

    def test_return_with_comprehension_wraps_as_code(self):
        """return with comprehension wraps as CODE comment."""
        result = convert_text(
            "$code:\n    x = [a for a in items]\n    return x",
            macro_name="Test",
        )
        assert "{# CODE:" in result


# ═══════════════════════════════════════════════════════════════════════════
# 6. $def with (macro definition)
# ═══════════════════════════════════════════════════════════════════════════


class TestDefWith:
    """Test $def with → {% macro %} conversion."""

    def test_def_with_simple(self):
        assert_convert(
            "$def with (name)\n<p>$name</p>",
            "{% macro Template(name) %}\n<p>{{ name }}</p>\n{% endmacro %}",
        )

    def test_def_with_defaults(self):
        assert_convert(
            '$def with (name="World")\n<p>Hello $name</p>',
            '{% macro Template(name="World") %}\n<p>Hello {{ name }}</p>\n{% endmacro %}',
        )

    def test_def_with_multiple_args(self):
        assert_convert(
            "$def with (a, b, c)\n<p>$a $b $c</p>",
            "{% macro Template(a, b, c) %}\n<p>{{ a }} {{ b }} {{ c }}</p>\n{% endmacro %}",
        )

    def test_def_with_mixed_args(self):
        assert_convert(
            "$def with (name, count=1, flag=False)\n<p>$name</p>",
            "{% macro Template(name, count=1, flag=False) %}\n<p>{{ name }}</p>\n{% endmacro %}",
        )

    def test_macro_name_from_param(self):
        assert_convert(
            "$def with (name)\n<p>$name</p>",
            "{% macro Greeting(name) %}\n<p>{{ name }}</p>\n{% endmacro %}",
            macro_name="Greeting",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. $def function definitions
# ═══════════════════════════════════════════════════════════════════════════


class TestDefFunction:
    """Test $def func(args): → {% macro %} conversion."""

    def test_def_function(self):
        assert_convert(
            "$def greet(name):\n    <p>Hello $name</p>\n\n$:greet('World')",
            "{% macro greet(name) %}\n    <p>Hello {{ name }}</p>\n{% endmacro %}\n\n{{ greet('World') | safe }}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. $code blocks
# ═══════════════════════════════════════════════════════════════════════════


class TestCodeBlocks:
    """Test $code: block conversion."""

    def test_code_simple_assignment(self):
        assert_convert(
            "$code:\n    x = 5\n    y = x + 1\n\n<p>$y</p>",
            "{% set x = 5 %}\n{% set y = x + 1 %}\n\n<p>{{ y }}</p>",
        )

    def test_code_with_function_def(self):
        assert_convert(
            "$code:\n    def format_name(a):\n        return a.name\n\n<p>$:format_name(author)</p>",
            "{% macro format_name(a) %}\n        {{ a.name }}\n{% endmacro %}\n\n<p>{{ format_name(author) | safe }}</p>",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 9. $cond() → Jinja ternary
# ═══════════════════════════════════════════════════════════════════════════


class TestCond:
    """Test $cond(expr, val) and $cond(expr, val, default) conversion."""

    def test_cond_two_args(self):
        assert_convert(
            "<span class=\"$cond(is_active, 'active')\">",
            "<span class=\"{{ 'active' if is_active else '' }}\">",
        )

    def test_cond_three_args(self):
        assert_convert(
            "<option $cond(is_selected, 'selected', '')>",
            "<option {{ 'selected' if is_selected else '' }}>",
        )

    def test_cond_with_method_call(self):
        assert_convert(
            '$cond(person.has_tag(t), "active")',
            "{{ \"active\" if person.has_tag(t) else '' }}",
        )

    def test_cond_with_loop_last(self):
        assert_convert(
            '$cond(loop.last, "", ", ")',
            '{{ "" if loop.last else ", " }}',
        )

    def test_cond_multiple_on_line(self):
        assert_convert(
            '$a $cond(x, "yes", "no") $b $cond(y, "on")',
            '{{ a }} {{ "yes" if x else "no" }} {{ b }} {{ "on" if y else \'\' }}',
        )

    def test_cond_in_attribute(self):
        assert_convert(
            '<button $cond(not can_save, "disabled")>',
            "<button {{ \"disabled\" if not can_save else '' }}>",
        )

    def test_cond_bare_in_set_context(self):
        """cond() without $ prefix appears when $ is stripped by RE_SET."""
        assert_convert(
            "$ rendered_name = cond(name, truncate(name, 40), _('Unknown author'))",
            "{% set rendered_name = truncate(name, 40) if name else _('Unknown author') %}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 10. $ungettext() passthrough
# ═══════════════════════════════════════════════════════════════════════════


class TestUngettext:
    """Test $ungettext() → {{ ungettext(...) }} conversion."""

    def test_ungettext_basic(self):
        assert_convert(
            '$ungettext("%(count)d book", "%(count)d books", count, count=count)',
            '{{ ungettext("%(count)d book", "%(count)d books", count, count=count) }}',
        )

    def test_ungettext_in_html(self):
        assert_convert(
            '<span>$ungettext("%(n)s item", "%(n)s items", n, n=n)</span>',
            '<span>{{ ungettext("%(n)s item", "%(n)s items", n, n=n) }}</span>',
        )

    def test_ungettext_with_variable_prefix(self):
        assert_convert(
            '<a href="/path">$ungettext("%(count)d work", "%(count)d works", page.work_count, count=page.work_count)</a>',
            '<a href="/path">{{ ungettext("%(count)d work", "%(count)d works", page.work_count, count=page.work_count) }}</a>',
        )


# ═══════════════════════════════════════════════════════════════════════════
# 11. Edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and unusual patterns."""

    def test_empty_input(self):
        assert convert_text("") == ""

    def test_blank_lines_preserved(self):
        assert_convert(
            "<p>First</p>\n\n<p>Second</p>",
            "<p>First</p>\n\n<p>Second</p>",
        )

    def test_no_dollar_signs(self):
        assert_convert(
            "<p>Hello World</p>",
            "<p>Hello World</p>",
        )

    def test_dollar_in_url(self):
        result = convert_text("Visit https://archive.org for details")
        assert "https://archive.org" in result

    def test_mixed_content_and_control(self):
        assert_convert(
            '$if user:\n    <div class="greeting">\n        <p>Hello $user.name</p>\n    </div>\n$else:\n    <p>Please log in</p>',
            '{% if user %}\n    <div class="greeting">\n        <p>Hello {{ user.name }}</p>\n    </div>\n{% else %}\n    <p>Please log in</p>\n{% endif %}',
        )


# ═══════════════════════════════════════════════════════════════════════════
# 12. Indentation sensitivity
# ═══════════════════════════════════════════════════════════════════════════


class TestIndentation:
    """Test that indentation-based block nesting is handled correctly."""

    def test_deeply_nested_blocks(self):
        assert_convert(
            "$for a in items:\n    $if a.show:\n        <p>$a.name</p>",
            "{% for a in items %}\n    {% if a.show %}\n        <p>{{ a.name }}</p>\n    {% endif %}\n{% endfor %}",
        )

    def test_block_closes_on_dedent(self):
        """Test that blocks close properly when indentation decreases."""
        assert_convert(
            "$if show:\n    <p>Shown</p>\n<p>Always</p>",
            "{% if show %}\n    <p>Shown</p>\n{% endif %}\n<p>Always</p>",
        )

    def test_multiple_sequential_blocks(self):
        assert_convert(
            "$if a:\n    <p>A</p>\n$if b:\n    <p>B</p>",
            "{% if a %}\n    <p>A</p>\n{% endif %}\n{% if b %}\n    <p>B</p>\n{% endif %}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# FULL TEMPLATE CONVERSIONS
# ═══════════════════════════════════════════════════════════════════════════


# ── Template 1: Hello.html (simplest) ────────────────────────────────────

HELLO_INPUT = """\
$def with (name="World", times=1)

$for i in range(times):
    <b>$_.hello, $name!</b><br/>
"""

HELLO_EXPECTED = """\
{% macro Hello(name="World", times=1) %}

{% for i in range(times) %}
    <b>{{ _.hello }}, {{ name }}!</b><br/>
{% endfor %}
{% endmacro %}"""


class TestTemplate1_Hello:
    """Test conversion of openlibrary/macros/Hello.html."""

    def test_full_conversion(self):
        result = convert_text(dedent(HELLO_INPUT), macro_name="Hello")
        assert result == dedent(HELLO_EXPECTED)

    def test_def_with_defaults(self):
        result = convert_text(dedent(HELLO_INPUT), macro_name="Hello")
        assert '{% macro Hello(name="World", times=1) %}' in result

    def test_for_loop(self):
        result = convert_text(dedent(HELLO_INPUT), macro_name="Hello")
        assert "{% for i in range(times) %}" in result
        assert "{% endfor %}" in result

    def test_attribute_access(self):
        result = convert_text(dedent(HELLO_INPUT), macro_name="Hello")
        assert "{{ _.hello }}" in result

    def test_variable_interpolation(self):
        result = convert_text(dedent(HELLO_INPUT), macro_name="Hello")
        assert "{{ name }}" in result

    def test_endmacro_present(self):
        result = convert_text(dedent(HELLO_INPUT), macro_name="Hello")
        assert "{% endmacro %}" in result


# ── Template 2: OlPagination.html ────────────────────────────────────────

OLPAGINATION_INPUT = """\
$def with (page, total_pages)

$if total_pages > 1:
    <div class="ol-pagination-wrapper">
        <ol-pagination
            total-pages="$total_pages"
            current-page="$page"
            label-previous-page="$_('Go to previous page')"
            label-next-page="$_('Go to next page')"
            label-go-to-page="$_('Go to page {page}')"
            label-current-page="$_('Page {page}, current page')"
            label-pagination="$_('Pagination')"
        ></ol-pagination>
    </div>
"""

OLPAGINATION_EXPECTED = """\
{% macro OlPagination(page, total_pages) %}

{% if total_pages > 1 %}
    <div class="ol-pagination-wrapper">
        <ol-pagination
            total-pages="{{ total_pages }}"
            current-page="{{ page }}"
            label-previous-page="{{ _('Go to previous page') }}"
            label-next-page="{{ _('Go to next page') }}"
            label-go-to-page="{{ _('Go to page {page}') }}"
            label-current-page="{{ _('Page {page}, current page') }}"
            label-pagination="{{ _('Pagination') }}"
        ></ol-pagination>
    </div>
{% endif %}
{% endmacro %}"""


class TestTemplate2_OlPagination:
    """Test conversion of openlibrary/macros/OlPagination.html."""

    def test_full_conversion(self):
        result = convert_text(dedent(OLPAGINATION_INPUT), macro_name="OlPagination")
        assert result == dedent(OLPAGINATION_EXPECTED)

    def test_if_condition(self):
        result = convert_text(dedent(OLPAGINATION_INPUT), macro_name="OlPagination")
        assert "{% if total_pages > 1 %}" in result
        assert "{% endif %}" in result

    def test_i18n_in_attributes(self):
        result = convert_text(dedent(OLPAGINATION_INPUT), macro_name="OlPagination")
        assert "{{ _('Go to previous page') }}" in result
        assert "{{ _('Go to next page') }}" in result
        assert "{{ _('Pagination') }}" in result

    def test_variables_in_attributes(self):
        result = convert_text(dedent(OLPAGINATION_INPUT), macro_name="OlPagination")
        assert 'total-pages="{{ total_pages }}"' in result
        assert 'current-page="{{ page }}"' in result

    def test_i18n_with_braces(self):
        """Ensure i18n strings containing {page} are preserved."""
        result = convert_text(dedent(OLPAGINATION_INPUT), macro_name="OlPagination")
        assert "{{ _('Go to page {page}') }}" in result


# ── Template 3: form.html ────────────────────────────────────────────────

FORM_INPUT = """\
$def with (form)

$if form.note:
    <div class="note">$form.note</div>

$for i in form.inputs:
    $ id = i.id or i.name
    $if i.is_hidden():
        $:i.render()
    $else:
        <div class="formElement">
            <div class="label"><label for="$i.id">$i.description</label> <span class="smaller lighter">$i.help</span></div>
            <div class="input">
                $:i.render()
            </div>
            $if "password" == i.id:
                <div class="input"><span id="showpass" class="smaller"></span></div>
            $if "new_password" == i.id:
                <div class="input"><span id="masker" class="smaller"></span></div>
            <div class="invalid clearfix" htmlfor="$i.id">$i.note</div>
        </div>
"""

FORM_EXPECTED = """\
{% macro form(form) %}

{% if form.note %}
    <div class="note">{{ form.note }}</div>
{% endif %}

{% for i in form.inputs %}
    {% set id = i.id or i.name %}
    {% if i.is_hidden() %}
        {{ i.render() | safe }}
    {% else %}
        <div class="formElement">
            <div class="label"><label for="{{ i.id }}">{{ i.description }}</label> <span class="smaller lighter">{{ i.help }}</span></div>
            <div class="input">
                {{ i.render() | safe }}
            </div>
            {% if "password" == i.id %}
                <div class="input"><span id="showpass" class="smaller"></span></div>
            {% endif %}
            {% if "new_password" == i.id %}
                <div class="input"><span id="masker" class="smaller"></span></div>
            {% endif %}
            <div class="invalid clearfix" htmlfor="{{ i.id }}">{{ i.note }}</div>
        </div>
    {% endif %}
{% endfor %}
{% endmacro %}"""


class TestTemplate3_Form:
    """Test conversion of openlibrary/templates/form.html."""

    def test_full_conversion(self):
        result = convert_text(dedent(FORM_INPUT), macro_name="form")
        assert result == dedent(FORM_EXPECTED)

    def test_nested_for_if_else(self):
        result = convert_text(dedent(FORM_INPUT), macro_name="form")
        assert result.count("{% for") == 1
        assert result.count("{% endfor %}") == 1
        assert result.count("{% if") >= 4
        assert result.count("{% else %}") >= 1

    def test_raw_output(self):
        result = convert_text(dedent(FORM_INPUT), macro_name="form")
        assert "{{ i.render() | safe }}" in result

    def test_set_statement(self):
        result = convert_text(dedent(FORM_INPUT), macro_name="form")
        assert "{% set id = i.id or i.name %}" in result

    def test_variable_in_attributes(self):
        result = convert_text(dedent(FORM_INPUT), macro_name="form")
        assert 'for="{{ i.id }}"' in result
        assert 'htmlfor="{{ i.id }}"' in result


# ── Template 4: CoverImage.html ──────────────────────────────────────────

COVERIMAGE_INPUT = """\
$def with(book, size="M")

$ title = book.title_prefix + " " + book.title

$ olid = book.key.split("/")[2]

$code:
    def aname(a):
        if isinstance(a, basestring):
            return a
        else:
            return a.name

$ author_names = ", ".join(aname(a) for a in book.authors) or book.get('by_statement','')

$ cover_url = book.get_cover_url(size)

$if size == "M":
    <div class="coverMagic cover-animation">
        $if cover_url:
            <div class="SRPCover bookCover">
                <img src="$cover_url" class="cover" alt="$title $_.by $author_names"/>
            </div>
        $else:
            <div class="SRPCoverBlank" style="display: block">
                <div class="innerBorder">
                    <div class="BookTitle">$:macros.TruncateString(title, 70)
                        <div class="Author">$:macros.TruncateString(author_names, 30)</div>
                    </div>
                </div>
            </div>
    </div>
$else:
    $if cover_url:
        <img src="$cover_url" height="58" title="$title" alt="$title"/>
    $else:
        <img src="/static/images/icons/avatar_book-sm.png" alt="$title"/>
"""

COVERIMAGE_EXPECTED = """\
{% macro CoverImage(book, size="M") %}

{% set title = book.title_prefix + " " + book.title %}

{% set olid = book.key.split("/")[2] %}

{% macro aname(a) %}
        {% if isinstance(a, basestring) %}
            {{ a }}
        {% else %}
            {{ a.name }}
        {% endif %}
{% endmacro %}

{# CODE: author_names = ", ".join(aname(a) for a in book.authors) or book.get('by_statement','') #}

{% set cover_url = book.get_cover_url(size) %}

{% if size == "M" %}
    <div class="coverMagic cover-animation">
        {% if cover_url %}
            <div class="SRPCover bookCover">
                <img src="{{ cover_url }}" class="cover" alt="{{ title }} {{ _.by }} {{ author_names }}"/>
            </div>
        {% else %}
            <div class="SRPCoverBlank" style="display: block">
                <div class="innerBorder">
                    <div class="BookTitle">{{ macros.TruncateString(title, 70) | safe }}
                        <div class="Author">{{ macros.TruncateString(author_names, 30) | safe }}</div>
                    </div>
                </div>
            </div>
        {% endif %}
    </div>
{% else %}
    {% if cover_url %}
        <img src="{{ cover_url }}" height="58" title="{{ title }}" alt="{{ title }}"/>
    {% else %}
        <img src="/static/images/icons/avatar_book-sm.png" alt="{{ title }}"/>
    {% endif %}
{% endif %}
{% endmacro %}"""


class TestTemplate4_CoverImage:
    """Test conversion of openlibrary/macros/CoverImage.html."""

    def test_full_conversion(self):
        result = convert_text(dedent(COVERIMAGE_INPUT), macro_name="CoverImage")
        assert result == dedent(COVERIMAGE_EXPECTED)

    def test_set_statements(self):
        result = convert_text(dedent(COVERIMAGE_INPUT), macro_name="CoverImage")
        assert '{% set title = book.title_prefix + " " + book.title %}' in result
        assert '{% set olid = book.key.split("/")[2] %}' in result

    def test_code_block_with_function(self):
        result = convert_text(dedent(COVERIMAGE_INPUT), macro_name="CoverImage")
        assert "{% macro aname(a) %}" in result
        assert "{% endmacro %}" in result

    def test_nested_conditionals(self):
        result = convert_text(dedent(COVERIMAGE_INPUT), macro_name="CoverImage")
        assert '{% if size == "M" %}' in result
        assert "{% if cover_url %}" in result

    def test_macro_calls_in_content(self):
        result = convert_text(dedent(COVERIMAGE_INPUT), macro_name="CoverImage")
        assert "{{ macros.TruncateString(title, 70) | safe }}" in result
        assert "{{ macros.TruncateString(author_names, 30) | safe }}" in result

    def test_multiple_variables_in_attribute(self):
        result = convert_text(dedent(COVERIMAGE_INPUT), macro_name="CoverImage")
        assert "{{ title }} {{ _.by }} {{ author_names }}" in result


# ── Template 5: QueryCarousel.html (most complex) ────────────────────────

QUERYCAROUSEL_INPUT = """\
$def with(query, title=None, sort='new', key='', limit=20, search=False, has_fulltext_only=True, url=None, layout='carousel', use_cache=True, lazy=True, user_lang_only=False, fallback=False, safe_mode=True)

$# Takes following parameters
$# * query (str) -- Any arbitrary Open Library search query, e.g. subject:"Textbooks"
$# * title (str) -- A title to show above the carousel (links to /search?q=query)
$# * sort (str) -- optional sort param defined within work_search.py `work_search`
$# * key (str) -- unique name of the carousel in analytics
$# * limit (int) -- initial number of books to pull
$# * search (bool) -- whether to include search within collection
$# * layout (str) -- layout type, default 'carousel', currently also supports 'grid'
$# * lazy (bool) -- When True, lazy-load this carousel
$# * use_cache (bool) -- Whether to cache this macro
$# * user_lang_only (bool) -- Whether to filter results by the user's language
$# * fallback (bool) -- Whether to show a fallback message if no results are found
$# * safe_mode (bool) -- When True, blurs covers of books that have a `content_warning` tag

$ fallback_query = None
$if user_lang_only:
  $ web_lang = get_lang() or 'en'
  $ user_lang= convert_iso_to_marc(web_lang)
  $if user_lang and user_lang in get_populated_languages():
        $ fallback_query = query
        $ query = query + ' language:' + user_lang

$ fallback = fallback and fallback_query

$if use_cache and not lazy:
    $# Note this won't work with fallback; the JS that handles retries is in lazy-carousel.js
    $:macros.CacheableMacro("RawQueryCarousel", query, title=title, sort=sort, key=key, limit=limit, search=search, has_fulltext_only=has_fulltext_only, url=url, layout=layout, fallback=fallback, safe_mode=safe_mode)
$else:
    $:macros.RawQueryCarousel(query, title=title, sort=sort, key=key, limit=limit, search=search, has_fulltext_only=has_fulltext_only, url=url, layout=layout, lazy=lazy, fallback=fallback, safe_mode=safe_mode)
"""

QUERYCAROUSEL_EXPECTED = """\
{% macro QueryCarousel(query, title=None, sort='new', key='', limit=20, search=False, has_fulltext_only=True, url=None, layout='carousel', use_cache=True, lazy=True, user_lang_only=False, fallback=False, safe_mode=True) %}

{# Takes following parameters #}
{# * query (str) -- Any arbitrary Open Library search query, e.g. subject:"Textbooks" #}
{# * title (str) -- A title to show above the carousel (links to /search?q=query) #}
{# * sort (str) -- optional sort param defined within work_search.py `work_search` #}
{# * key (str) -- unique name of the carousel in analytics #}
{# * limit (int) -- initial number of books to pull #}
{# * search (bool) -- whether to include search within collection #}
{# * layout (str) -- layout type, default 'carousel', currently also supports 'grid' #}
{# * lazy (bool) -- When True, lazy-load this carousel #}
{# * use_cache (bool) -- Whether to cache this macro #}
{# * user_lang_only (bool) -- Whether to filter results by the user's language #}
{# * fallback (bool) -- Whether to show a fallback message if no results are found #}
{# * safe_mode (bool) -- When True, blurs covers of books that have a `content_warning` tag #}

{% set fallback_query = None %}
{% if user_lang_only %}
  {% set web_lang = get_lang() or 'en' %}
  {% set user_lang = convert_iso_to_marc(web_lang) %}
  {% if user_lang and user_lang in get_populated_languages() %}
        {% set fallback_query = query %}
        {% set query = query + ' language:' + user_lang %}
  {% endif %}
{% endif %}
{% set fallback = fallback and fallback_query %}

{% if use_cache and not lazy %}
    {# Note this won't work with fallback; the JS that handles retries is in lazy-carousel.js #}
    {{ macros.CacheableMacro("RawQueryCarousel", query, title=title, sort=sort, key=key, limit=limit, search=search, has_fulltext_only=has_fulltext_only, url=url, layout=layout, fallback=fallback, safe_mode=safe_mode) | safe }}
{% else %}
    {{ macros.RawQueryCarousel(query, title=title, sort=sort, key=key, limit=limit, search=search, has_fulltext_only=has_fulltext_only, url=url, layout=layout, lazy=lazy, fallback=fallback, safe_mode=safe_mode) | safe }}
{% endif %}
{% endmacro %}"""


class TestTemplate5_QueryCarousel:
    """Test conversion of openlibrary/macros/QueryCarousel.html."""

    def test_full_conversion(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert result == dedent(QUERYCAROUSEL_EXPECTED)

    def test_many_default_args(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert "use_cache=True" in result
        assert "safe_mode=True" in result

    def test_comment_block(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert "{# Takes following parameters #}" in result
        assert "{# * query (str)" in result
        assert "{# Note this won't work with fallback" in result

    def test_nested_if_in_if(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert "{% if user_lang_only %}" in result
        assert "{% if user_lang and user_lang in get_populated_languages() %}" in result

    def test_set_statements(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert "{% set fallback_query = None %}" in result
        assert "{% set fallback = fallback and fallback_query %}" in result

    def test_macro_calls(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert "macros.CacheableMacro(" in result
        assert "macros.RawQueryCarousel(" in result

    def test_if_else_structure(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert "{% if use_cache and not lazy %}" in result
        assert "{% else %}" in result
        assert result.count("{% endif %}") >= 3

    def test_string_concatenation_preserved(self):
        result = convert_text(dedent(QUERYCAROUSEL_INPUT), macro_name="QueryCarousel")
        assert "query + ' language:' + user_lang" in result


# ═══════════════════════════════════════════════════════════════════════════
# 13. File-based conversion
# ═══════════════════════════════════════════════════════════════════════════


class TestFileConversion:
    """Test convert_file function with actual OL template files."""

    @pytest.fixture
    def hello_path(self):
        return os.path.join(os.path.dirname(__file__), "..", "..", "openlibrary", "macros", "Hello.html")

    def test_convert_hello_file(self, hello_path):
        if not os.path.exists(hello_path):
            pytest.skip("Hello.html not found in expected location")
        result = convert_file(hello_path, macro_name="Hello")
        assert "{% macro Hello(" in result
        assert "{% for i in range(times) %}" in result
        assert "{{ _.hello }}" in result
        assert "{% endfor %}" in result
        assert "{% endmacro %}" in result


# ═══════════════════════════════════════════════════════════════════════════
# 14. Converter class unit tests
# ═══════════════════════════════════════════════════════════════════════════


class TestConverterClass:
    """Test the TempletorToJinjaConverter class directly."""

    def test_init_default(self):
        c = TempletorToJinjaConverter()
        assert c.macro_name == ""

    def test_init_with_name(self):
        c = TempletorToJinjaConverter(macro_name="Test")
        assert c.macro_name == "Test"

    def test_convert_empty(self):
        c = TempletorToJinjaConverter()
        assert c.convert("") == ""

    def test_convert_whitespace_only(self):
        c = TempletorToJinjaConverter()
        # Whitespace-only input is normalized to empty (no meaningful content)
        assert c.convert("   \n   ") == ""

    def test_get_end_tag(self):
        assert TempletorToJinjaConverter._get_end_tag("for") == "{% endfor %}"
        assert TempletorToJinjaConverter._get_end_tag("if") == "{% endif %}"
        assert TempletorToJinjaConverter._get_end_tag("macro") == "{% endmacro %}"


# ═══════════════════════════════════════════════════════════════════════════
# 15. Jinja2 compilation validation
# ═══════════════════════════════════════════════════════════════════════════


class TestJinja2Compilation:
    """Verify all converted macro templates compile as valid Jinja2."""

    @pytest.fixture
    def macros_dir(self):
        return os.path.join(os.path.dirname(__file__), "..", "..", "openlibrary", "macros")

    def test_all_macros_compile_with_jinja2(self, macros_dir):
        """Every openlibrary/macros/*.html must convert to parseable Jinja2."""
        jinja2 = pytest.importorskip("jinja2")
        env = jinja2.Environment()

        if not os.path.isdir(macros_dir):
            pytest.skip("macros directory not found")

        files = sorted(f for f in os.listdir(macros_dir) if f.endswith(".html"))
        assert len(files) > 0, "No macro files found"

        failures = []
        for f in files:
            name = f.replace(".html", "")
            path = os.path.join(macros_dir, f)
            try:
                result = convert_file(path, macro_name=name)
                env.parse(result)
            except jinja2.TemplateSyntaxError as e:
                lines = result.split("\n")
                err_line = lines[e.lineno - 1].strip()[:120] if e.lineno <= len(lines) else "??"
                failures.append(f"{name} (L{e.lineno}): {e.message}\n    >>> {err_line}")
            except Exception as e:
                failures.append(f"{name}: {e}")

        assert failures == [], f"{len(failures)}/{len(files)} templates failed Jinja2 compilation:\n" + "\n".join(failures)
