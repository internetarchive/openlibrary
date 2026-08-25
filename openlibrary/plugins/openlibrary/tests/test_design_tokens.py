"""Tests for the design-token CSS parser behind /developers/design/foundations."""

from pathlib import Path

import pytest

from openlibrary.plugins.openlibrary.design_tokens import (
    _clean_comment,
    _drop_internal,
    _parse_file,
    _resolve,
    load_token_categories,
)


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def text_of(blocks) -> list[tuple[str, str]]:
    """Each block as (kind, text) — list items joined so one assert covers both."""
    return [(block.kind, " | ".join(block.items) if block.kind == "list" else block.text) for block in blocks]


class TestCleanComment:
    def test_strips_gutter_and_decoration_rules(self):
        title, blocks = _clean_comment("*\n * Colors\n * ======\n * Two-tier system.\n ")
        assert (title, text_of(blocks)) == ("Colors", [("paragraph", "Two-tier system.")])

    def test_splits_long_first_line_at_first_sentence(self):
        title, blocks = _clean_comment(" Muted status ramps. The 600/700 steps are the text-safe foregrounds\n (AA on white).\n")
        assert title == "Muted status ramps."
        assert text_of(blocks) == [("paragraph", "The 600/700 steps are the text-safe foregrounds (AA on white).")]

    def test_keeps_short_first_line_with_a_period_intact(self):
        title, _ = _clean_comment(" 1. Primitives\n -------------\n")
        assert title == "1. Primitives"

    def test_trims_dangling_punctuation_from_a_heading(self):
        title, blocks = _clean_comment(" Environment badge & favicon —\n\n values match the favicons\n")
        assert title == "Environment badge & favicon"
        assert text_of(blocks) == [("paragraph", "values match the favicons")]

    def test_preserves_whitespace_for_box_drawing_diagrams(self):
        title, blocks = _clean_comment(" ---- Inline ----\n\n   ┌───┐ ↔ ┌───┐\n   │ A │   │ B │\n")
        assert title == "Inline"
        assert text_of(blocks) == [("pre", "┌───┐ ↔ ┌───┐\n│ A │   │ B │")]

    def test_arrows_alone_are_prose_not_a_diagram(self):
        _, blocks = _clean_comment(" Blues → blue ramp\n\n Re-pointed at the ramp.")
        assert text_of(blocks) == [("paragraph", "Re-pointed at the ramp.")]


class TestHeadings:
    """The first line is only a heading when it reads like one."""

    def test_a_line_followed_by_a_rule_is_a_heading(self):
        assert _clean_comment(" Spacing Primitives\n ====\n Based on a 4px grid.")[0] == "Spacing Primitives"

    def test_a_line_followed_by_a_blank_is_a_heading(self):
        assert _clean_comment(" Layout: page-level spacing\n\n Use for: page edge margins")[0] == "Layout: page-level spacing"

    def test_a_lone_line_is_a_heading(self):
        assert _clean_comment(" Text ")[0] == "Text"

    def test_a_short_line_closing_its_own_sentence_is_a_heading(self):
        title, blocks = _clean_comment(' Warm neutral ramp — "paper to ink".\n Replaces the legacy grey families.')
        assert title == 'Warm neutral ramp — "paper to ink".'
        assert text_of(blocks) == [("paragraph", "Replaces the legacy grey families.")]

    def test_a_wrapped_first_line_is_body_prose_not_a_heading(self):
        """Splitting mid-clause left headings like "…, saturated border" on the page."""
        title, blocks = _clean_comment(" Selected state for neutral controls — soft blue tint, saturated border,\n dark-blue text. Shared by ol-button.")
        assert title == ""
        assert text_of(blocks) == [("paragraph", "Selected state for neutral controls — soft blue tint, saturated border, dark-blue text. Shared by ol-button.")]


class TestBlocks:
    def test_a_numbered_list_survives_as_a_list(self):
        comment = (
            " Colors\n ======\n Two-tier token system:\n\n"
            "   1. Primitives — raw ramps. Never use directly\n      in component styles.\n"
            "   2. Semantic tokens — purpose-named.\n"
        )
        _, blocks = _clean_comment(comment)
        assert text_of(blocks) == [
            ("paragraph", "Two-tier token system:"),
            ("list", "Primitives — raw ramps. Never use directly in component styles. | Semantic tokens — purpose-named."),
        ]
        assert blocks[1].ordered is True

    def test_a_bulleted_list_is_unordered(self):
        _, blocks = _clean_comment(" Rules\n =====\n - One source of truth.\n - Controls set height.\n")
        assert blocks[0].kind == "list"
        assert blocks[0].ordered is False

    def test_a_blank_line_starts_a_new_paragraph(self):
        _, blocks = _clean_comment(" Notes\n =====\n First point\n continued.\n\n Second point.\n")
        assert text_of(blocks) == [("paragraph", "First point continued."), ("paragraph", "Second point.")]

    def test_an_indented_run_is_preformatted_and_dedented(self):
        _, blocks = _clean_comment(" Breakpoints\n ===========\n Example:\n\n   @media (min-width: 768px) { ... }\n")
        assert text_of(blocks) == [("paragraph", "Example:"), ("pre", "@media (min-width: 768px) { ... }")]

    def test_an_indented_body_is_prose_not_an_example(self):
        """Every line indented the same way is just how the comment was laid out."""
        _, blocks = _clean_comment(" Raised-control drop shadow.\n     Shared by buttons\n     and the segmented control.\n")
        assert text_of(blocks) == [("paragraph", "Shared by buttons and the segmented control.")]

    def test_a_pipe_table_survives_as_a_table(self):
        comment = " Colors\n ======\n Which token?\n\n | Styling | Use |\n |---|---|\n | Body text | `--color-text` |\n"
        _, blocks = _clean_comment(comment)
        assert text_of(blocks) == [("paragraph", "Which token?"), ("table", "")]
        assert blocks[1].headers == ("Styling", "Use")
        assert blocks[1].rows == (("Body text", "`--color-text`"),)

    def test_pipe_rows_without_a_header_rule_stay_prose(self):
        """No rule means no header row, and inventing one would mislabel the run."""
        _, blocks = _clean_comment(" Notes\n =====\n | a | b |\n | c | d |\n")
        assert text_of(blocks) == [("paragraph", "| a | b | | c | d |")]


class TestParseFile:
    def test_opening_comment_becomes_the_category_blurb_when_it_restates_the_filename(self, tmp_path):
        category = _parse_file(write(tmp_path, "colors.css", "/**\n * Colors\n * ======\n * Two-tier system.\n */\n:root { --blue-500: hsl(202, 96%, 37%); }\n"))
        assert (category.id, category.title) == ("colors", "Colors")
        assert text_of(category.blurb) == [("paragraph", "Two-tier system.")]
        assert category.groups[0].title == ""

    def test_opening_comment_stays_a_group_heading_when_it_names_a_tier(self, tmp_path):
        category = _parse_file(
            write(tmp_path, "border-radius.css", "/**\n * Border-Radius Primitives\n * ====\n * Rarely used directly.\n */\n:root { --border-radius-sm: 3px; }\n")
        )
        assert (category.title, category.blurb) == ("Border Radius", [])
        assert category.groups[0].title == "Border-Radius Primitives"

    def test_trailing_comment_documents_the_token_it_follows(self, tmp_path):
        category = _parse_file(
            write(tmp_path, "c.css", ":root {\n  --neutral-50: hsl(48, 44%, 97%); /* lightest tint */\n  --neutral-900: hsl(40, 16%, 12%);\n}\n")
        )
        tokens = category.groups[0].tokens
        assert tokens[0].description == "lightest tint"
        assert tokens[1].description == ""

    def test_non_trailing_comment_opens_a_new_group(self, tmp_path):
        category = _parse_file(write(tmp_path, "c.css", ":root {\n  /* Text */\n  --color-text: red;\n  /* Surfaces */\n  --color-surface: white;\n}\n"))
        assert [(group.title, len(group.tokens)) for group in category.groups] == [("Text", 1), ("Surfaces", 1)]

    def test_a_declaration_inside_a_comment_is_not_parsed_as_a_token(self, tmp_path):
        category = _parse_file(write(tmp_path, "c.css", ":root {\n  /* Prefer:\n     box-shadow: var(--x);\n     --not-a-token: 1px; */\n  --real: 2px;\n}\n"))
        assert [token.name for group in category.groups for token in group.tokens] == ["--real"]

    def test_group_with_no_tokens_is_kept_as_a_standalone_heading(self, tmp_path):
        category = _parse_file(write(tmp_path, "c.css", "/**\n * 2. Semantic tokens\n * ---\n */\n:root { }\n/* Text */\n:root { --color-text: red; }\n"))
        assert [(group.title, len(group.tokens)) for group in category.groups] == [("2. Semantic tokens", 0), ("Text", 1)]

    def test_a_responsive_override_does_not_redeclare_its_token(self, tmp_path):
        """One token, one row: the phone value is the same token, not a second one.

        Its introducing comment goes with it, or it would head a group of nothing.
        """
        body = ":root { --size: 57px; }\n/* Steps down on phones. */\n@media (max-width: 768px) {\n  :root { --size: 45px; }\n}\n"
        category = _parse_file(write(tmp_path, "c.css", body))
        assert [(group.title, [token.name for token in group.tokens]) for group in category.groups] == [("", ["--size"])]

    def test_a_brace_inside_a_comment_does_not_end_the_masked_block(self, tmp_path):
        """Braces are counted off a comment-stripped copy, so prose can't close the block early.

        breakpoints.css documents `@media (min-width: 768px) { ... }` in a comment;
        counting that brace would swallow the real :root below and empty the category.
        """
        body = "@media (max-width: 768px) {\n  /* --color-{a,b} */\n  :root { --hidden: 1px; }\n}\n:root { --kept: 2px; }\n"
        category = _parse_file(write(tmp_path, "c.css", body))
        assert [token.name for group in category.groups for token in group.tokens] == ["--kept"]

    def test_a_stray_comment_close_above_a_block_does_not_raise(self, tmp_path):
        """A `*/` closing no comment stops the walk-back instead of killing the page.

        load_token_categories() only catches OSError, so a KeyError here would 500
        /developers/design rather than cost one lead-in comment.
        """
        body = "/* a */ */\n@media (max-width: 768px) {\n  :root { --hidden: 1px; }\n}\n:root { --kept: 2px; }\n"
        category = _parse_file(write(tmp_path, "c.css", body))
        assert [token.name for group in category.groups for token in group.tokens] == ["--kept"]


class TestRamps:
    def test_a_numeric_color_run_is_a_ramp_and_a_stray_sibling_stays_loose(self, tmp_path):
        body = """:root {
            /* Warm neutral */
            --neutral-50: hsl(48, 44%, 97%);
            --neutral-100: hsl(48, 36%, 94%);
            --neutral-200: hsl(47, 31%, 86%);
            --white: hsl(0, 0%, 100%);
        }
        """
        group = _parse_file(write(tmp_path, "colors.css", body)).groups[0]
        assert [(prefix, len(tokens)) for prefix, tokens in group.ramps] == [("--neutral", 3)]
        assert [token.name for token in group.loose_tokens] == ["--white"]

    def test_one_group_can_hold_several_ramps(self, tmp_path):
        body = """:root {
            /* Status */
            --red-50: hsl(8, 75%, 96%);
            --red-100: hsl(8, 72%, 92%);
            --red-500: hsl(8, 64%, 42%);
            --green-50: hsl(128, 45%, 94%);
            --green-100: hsl(128, 45%, 90%);
            --green-500: hsl(130, 50%, 30%);
        }
        """
        group = _parse_file(write(tmp_path, "colors.css", body)).groups[0]
        assert [prefix for prefix, _ in group.ramps] == ["--red", "--green"]

    def test_a_numeric_run_that_is_not_colors_is_not_a_ramp(self, tmp_path):
        body = ":root {\n  /* Levels */\n  --z-index-level-1: 1;\n  --z-index-level-2: 2;\n  --z-index-level-3: 3;\n}\n"
        group = _parse_file(write(tmp_path, "z-index.css", body)).groups[0]
        assert group.ramps == []
        assert len(group.loose_tokens) == 3

    def test_two_steps_are_too_few_to_be_a_ramp(self, tmp_path):
        body = ":root {\n  /* Pinks */\n  --pink-50: hsl(1, 2%, 3%);\n  --pink-100: hsl(1, 2%, 4%);\n}\n"
        group = _parse_file(write(tmp_path, "colors.css", body)).groups[0]
        assert group.ramps == []


class TestResolve:
    def test_alias_chains_resolve_to_the_concrete_value(self, tmp_path):
        body = ":root {\n  --blue-600: hsl(202, 96%, 28%);\n  --link-blue: var(--blue-600);\n  --color-link: var(--link-blue);\n}\n"
        category = _parse_file(write(tmp_path, "colors.css", body))
        _resolve([category])
        tokens = {token.name: token for group in category.groups for token in group.tokens}
        assert tokens["--color-link"].reference == "--link-blue"
        assert tokens["--color-link"].resolved == "hsl(202, 96%, 28%)"
        assert tokens["--color-link"].display_value == "hsl(202, 96%, 28%)"

    def test_a_self_referential_chain_does_not_hang(self, tmp_path):
        category = _parse_file(write(tmp_path, "c.css", ":root {\n  --a: var(--b);\n  --b: var(--a);\n}\n"))
        _resolve([category])
        tokens = {token.name: token for group in category.groups for token in group.tokens}
        assert tokens["--a"].resolved == ""
        # Falls back to the literal declaration so the row still shows something.
        assert tokens["--a"].display_value == "var(--b)"

    def test_a_dangling_reference_leaves_the_token_unresolved(self, tmp_path):
        category = _parse_file(write(tmp_path, "c.css", ":root { --a: var(--missing); }"))
        _resolve([category])
        assert category.groups[0].tokens[0].resolved == ""


class TestTokenProperties:
    @pytest.mark.parametrize(
        ("value", "is_color"),
        [
            ("hsl(202, 96%, 37%)", True),
            ("#fff", True),
            ("color-mix(in srgb, var(--blue-500) 8%, transparent)", True),
            ("1px solid hsl(0, 0%, 87%)", False),
            ("0 0 0 2px hsl(202, 96%, 37%)", False),
            ("12px", False),
        ],
    )
    def test_is_color_only_matches_a_bare_color_value(self, tmp_path, value, is_color):
        category = _parse_file(write(tmp_path, "c.css", f":root {{ --x: {value}; }}"))
        assert category.groups[0].tokens[0].is_color is is_color

    def test_a_marker_never_reaches_the_rendered_note(self, tmp_path):
        """Markers are UI — they set a flag and are stripped, not shown as prose."""
        category = _parse_file(write(tmp_path, "c.css", ":root {\n  --old: red; /* @deprecated use --color-text */\n}\n"))
        assert category.groups[0].tokens[0].description == "use --color-text"

    def test_reference_is_derived_from_the_value(self, tmp_path):
        body = ":root {\n  --alias: var(--blue-500);\n  --literal: hsl(202, 96%, 37%);\n  --compound: 1px solid var(--blue-500);\n}\n"
        tokens = _parse_file(write(tmp_path, "c.css", body)).groups[0].tokens
        assert [token.reference for token in tokens] == ["--blue-500", "", ""]


class TestDropInternal:
    body = """
        /* 2. Semantic tokens */
        :root { }
        /* Text */
        :root { --color-text: red; }
        /* Component tokens @internal */
        :root { }
        /* Chips */
        :root { --color-chip-bg: blue; }
        /* 3. Deprecated aliases */
        :root { }
        /* Greys */
        :root { --grey: grey; }
        """

    def titles(self, tmp_path, body: str) -> list[str]:
        category = _parse_file(write(tmp_path, "colors.css", body))
        _drop_internal([category])
        return [group.title for group in category.groups]

    def test_a_marked_tier_takes_its_groups_with_it(self, tmp_path):
        titles = self.titles(tmp_path, self.body)
        assert "Component tokens @internal" not in titles
        assert "Chips" not in titles

    def test_the_next_tier_ends_the_marked_run(self, tmp_path):
        assert self.titles(tmp_path, self.body)[-2:] == ["3. Deprecated aliases", "Greys"]

    def test_an_unmarked_file_is_left_alone(self, tmp_path):
        body = ":root {\n  /* Text */\n  --color-text: red;\n  /* Surfaces */\n  --color-surface: white;\n}\n"
        assert self.titles(tmp_path, body) == ["Text", "Surfaces"]


class TestRealTokenFiles:
    """Guards against the shipped token files drifting out of what the page can read."""

    def test_every_category_parses_and_carries_tokens(self):
        categories = load_token_categories()
        assert {category.id for category in categories} >= {"colors", "spacing", "font-families", "z-index"}
        for category in categories:
            assert any(group.tokens for group in category.groups), f"{category.id} parsed no tokens"

    def test_the_color_ramps_are_found(self):
        colors = next(category for category in load_token_categories() if category.id == "colors")
        prefixes = {prefix for group in colors.groups for prefix, _ in group.ramps}
        assert {"--neutral", "--blue", "--red", "--green", "--amber"} <= prefixes

    def test_semantic_color_tokens_resolve_to_a_primitive(self):
        colors = next(category for category in load_token_categories() if category.id == "colors")
        tokens = {token.name: token for group in colors.groups for token in group.tokens}
        assert tokens["--color-text"].resolved.startswith("hsl(")
        assert tokens["--color-link"].resolved.startswith("hsl(")

    def test_the_colors_file_carries_the_which_token_do_i_use_table(self):
        """The one place a contributor is told how to choose; it renders or it doesn't exist.

        Read from the whole file, not the opening comment: the guide is free to
        live in its own section.
        """
        colors = next(category for category in load_token_categories() if category.id == "colors")
        blurbs = [colors.blurb, *(group.blurb for group in colors.groups)]
        table = next(block for blurb in blurbs for block in blurb if block.kind == "table")
        assert len(table.headers) == 2
        assert ("Body text", "`--color-text`") in table.rows

    def test_the_deprecated_alias_tier_is_flagged(self):
        colors = next(category for category in load_token_categories() if category.id == "colors")
        assert any(group.deprecated and group.tokens for group in colors.groups)

    def test_component_specific_color_tokens_are_not_documented(self):
        """They belong to one component each, so Foundations leaves them out."""
        names = {token.name for category in load_token_categories() for group in category.groups for token in group.tokens}
        assert "--color-text" in names
        assert not {name for name in names if name.startswith(("--color-chip-", "--book-cover-", "--admin-"))}

    def test_no_token_is_declared_twice(self):
        """A shadowed token would make the parsed label disagree with the browser."""
        seen: set[str] = set()
        duplicates = set()
        for category in load_token_categories():
            for group in category.groups:
                for token in group.tokens:
                    if token.name in seen:
                        duplicates.add(token.name)
                    seen.add(token.name)
        assert not duplicates, f"declared more than once: {sorted(duplicates)}"
