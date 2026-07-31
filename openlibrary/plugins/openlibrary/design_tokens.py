"""Parse the design-token CSS into a structure the design system page can render.

The token files in ``static/css/tokens/`` are already documented with block
comments — tier headers ("1. Primitives"), group labels ("Text", "Surfaces"),
and per-token trailing notes ("muted text — 5.0:1 on white"). This module reads
that structure out of the CSS so /developers/design/foundations can never drift
from the tokens themselves.

Note that parsed values are only ever used as *labels*. Swatches and other
previews render with ``var(--token)`` so the browser resolves them, which keeps
the page truthful for values Python can't evaluate (``color-mix()``, deep
``var()`` chains).
"""

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

TOKENS_DIR = Path(__file__).parents[3] / "static" / "css" / "tokens"
BARREL_PATH = TOKENS_DIR.parent / "tokens.css"

# Either a block comment or a custom-property declaration, whichever comes first.
# Comments are matched first in the alternation so a declaration-looking string
# inside a comment is consumed as prose rather than picked up as a token.
_SCAN_RE = re.compile(r"/\*(?P<comment>.*?)\*/|(?P<name>--[\w-]+)\s*:\s*(?P<value>[^;{}]+);", re.DOTALL)
_IMPORT_RE = re.compile(r"""@import\s+["']tokens/([\w-]+)\.css["']""")
_VAR_RE = re.compile(r"^var\(\s*(--[\w-]+)\s*\)$")
_RAMP_RE = re.compile(r"^(--[\w-]+?)-(\d+)$")
_DECORATION_RE = re.compile(r"^[\s*=~_-]+$")
_LIST_ITEM_RE = re.compile(r"^(?P<marker>[-*•]|\d+\.)\s+(?P<text>\S.*)$")
_DEPRECATED_RE = re.compile(r"\s*@deprecated\s*")
# Box-drawing characters mark a line as ASCII art (see spacing.css), which has
# to keep its whitespace to line up. Arrows are deliberately excluded — they
# show up in ordinary prose ("Blues → blue ramp").
_DIAGRAM_CHARS = set("┌┐└┘├┤┬┴┼─│")
# An indented run inside a comment is an example or a table (the @media snippet
# in breakpoints.css, the layer hierarchy in z-index.css), not prose.
_PRE_INDENT = 2
_COLOR_PREFIXES = ("#", "hsl", "rgb", "color-mix", "oklch", "oklab", "lab", "lch")
_TITLE_SPLIT_LENGTH = 60
_MIN_RAMP_STEPS = 3
# Marks a tier as belonging to one component rather than the shared vocabulary.
# Written in the CSS next to the tier heading, like ``@deprecated``.
_INTERNAL_MARKER = "@internal"
# Reading order for the Foundations page. Anything not listed sorts to the end.
_DISPLAY_ORDER = ("colors", "font-families", "line-heights", "spacing", "border-radius", "borders", "control-heights", "z-index", "breakpoints")


@dataclass(frozen=True)
class Block:
    """One run of a comment body: a paragraph, a list, or preformatted text.

    Comments in the token files are written for a reader — numbered tiers,
    bulleted rules, indented examples — so the body is parsed into blocks rather
    than flattened into one paragraph, which turned a three-item list into an
    unreadable run-on sentence.
    """

    kind: str
    text: str = ""
    items: tuple[str, ...] = ()
    ordered: bool = False


@dataclass(frozen=True)
class Token:
    """One custom property, with the trailing comment that documents it."""

    name: str
    value: str
    description: str = ""
    reference: str = ""
    resolved: str = ""

    @property
    def deprecated(self) -> bool:
        return "@deprecated" in self.description

    @property
    def display_value(self) -> str:
        """The resolved primitive if this token is a plain alias, else its own value."""
        return self.resolved or self.value

    @property
    def is_color(self) -> bool:
        return self.display_value.lower().startswith(_COLOR_PREFIXES)


@dataclass
class TokenGroup:
    """A run of tokens sharing one heading.

    Headings come from any comment that isn't trailing a declaration, so both
    the file's tier headers and its inline labels produce groups. A group with
    no tokens is a standalone heading (e.g. "1. Primitives"), and one with no
    title is a run of tokens introduced by prose alone.
    """

    title: str = ""
    blurb: list[Block] = field(default_factory=list)
    tokens: list[Token] = field(default_factory=list)
    deprecated: bool = False

    @property
    def display_title(self) -> str:
        return re.sub(r"\s+", " ", self.title).strip()

    @property
    def ramps(self) -> list[tuple[str, list[Token]]]:
        """Every ``<prefix>-<number>`` ramp of three or more steps, in source order.

        Groups can hold more than one ramp (the status group defines red, green
        and amber together) and can mix a ramp with standalone tokens (the
        neutral ramp sits alongside ``--white``), so this returns a list rather
        than classifying the group as a whole. Only colors qualify — a numeric
        run like ``--z-index-level-*`` has nothing to show as a strip.
        """
        by_prefix: dict[str, list[Token]] = {}
        for token in self.tokens:
            if (match := _RAMP_RE.match(token.name)) and token.is_color:
                by_prefix.setdefault(match.group(1), []).append(token)
        return [(prefix, tokens) for prefix, tokens in by_prefix.items() if len(tokens) >= _MIN_RAMP_STEPS]

    @property
    def loose_tokens(self) -> list[Token]:
        """Tokens that aren't part of a ramp, and so render as ordinary rows."""
        in_ramp = {token.name for _, tokens in self.ramps for token in tokens}
        return [token for token in self.tokens if token.name not in in_ramp]


@dataclass
class TokenCategory:
    """One token file — its header comment plus every group inside it."""

    id: str
    title: str
    blurb: list[Block]
    groups: list[TokenGroup]

    @property
    def anchor(self) -> str:
        return f"tokens-{self.id}"

    @property
    def has_colors(self) -> bool:
        return any(token.is_color for group in self.groups for token in group.tokens)


def _trim_blank(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


def _dedent(lines: list[str]) -> list[str]:
    """Remove the common leading whitespace, so indentation is relative.

    Comment bodies are indented to sit under their opening ``/*``, at wildly
    different depths. What matters is which lines are indented *further* than
    their neighbours, since that is what marks an example block.
    """
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    base = min(indents, default=0)
    return [line[base:] if line.strip() else "" for line in lines]


def _blocks(lines: list[str]) -> list[Block]:
    """Group a dedented comment body into paragraphs, lists and preformatted runs.

    A blank line always ends a block; within a block, the kind of each line
    decides. List continuation lines are indented, so the list case is checked
    before the indentation one.
    """
    blocks: list[Block] = []
    paragraph: list[str] = []
    pre: list[str] = []
    items: list[list[str]] = []
    ordered = False

    def flush() -> None:
        nonlocal paragraph, pre, items
        if paragraph:
            blocks.append(Block("paragraph", text=" ".join(paragraph)))
            paragraph = []
        if pre:
            # Dedented again on its own: the indent that marked the run as
            # preformatted is not indentation the reader should see.
            blocks.append(Block("pre", text="\n".join(_dedent(pre))))
            pre = []
        if items:
            blocks.append(Block("list", items=tuple(" ".join(item) for item in items), ordered=ordered))
            items = []

    for line in lines:
        stripped = line.strip()
        indented = len(line) - len(line.lstrip()) >= _PRE_INDENT
        if not stripped:
            flush()
        elif match := _LIST_ITEM_RE.match(stripped):
            if not items:
                flush()
                ordered = match.group("marker").endswith(".")
            items.append([match.group("text")])
        elif items and indented:
            items[-1].append(stripped)
        elif indented or any(char in _DIAGRAM_CHARS for char in line):
            if not pre:
                flush()
            pre.append(line)
        else:
            if not paragraph:
                flush()
            paragraph.append(stripped)
    flush()
    return blocks


def _flatten(blocks: list[Block]) -> str:
    """The blocks as one line, for places that render plain text (token notes)."""
    return " ".join(" ".join(block.items) if block.kind == "list" else block.text for block in blocks).strip()


def _clean_comment(raw: str) -> tuple[str, list[Block]]:
    """Split a block comment into a title and the blocks that make up its body.

    The first line is only a heading when it reads like one: underlined with a
    rule, followed by a blank line, or a short line closing with its own
    punctuation. A long first line is cut at its first sentence, and anything
    else is treated as the opening of a wrapped sentence and left in the body \u2014
    otherwise a heading ends up breaking mid-clause.
    """
    lines = _trim_blank([re.sub(r"^\s*\*[ \t]?", "", line).rstrip() for line in raw.split("\n")])
    if not lines:
        return "", []

    first, rest = lines[0], lines[1:]
    after = rest[0] if rest else ""
    underlined = bool(after.strip()) and bool(_DECORATION_RE.match(after))
    separated = not after.strip()
    # Dedent before prepending anything below, so a line pulled out of the
    # heading lines up with the body it belongs to rather than resetting it.
    rest = _dedent(_trim_blank([line for line in rest if not (line.strip() and _DECORATION_RE.match(line))]))

    # The escapes are the em and en dashes, spelled out so the literal is
    # unambiguous. Leading dashes come from "---- Inline ----" style headings.
    heading = first.strip().strip("-").strip().rstrip(" ,;:-\u2014\u2013")
    if underlined or separated:
        return heading, _blocks(rest)
    if len(heading) <= _TITLE_SPLIT_LENGTH and first.rstrip().endswith((".", ":", "!", "?")):
        return heading, _blocks(rest)
    if len(heading) > _TITLE_SPLIT_LENGTH and ". " in heading:
        head, _, tail = heading.partition(". ")
        return f"{head}.", _blocks([tail, *rest])
    return "", _blocks([first.strip(), *rest])


def _parse_file(path: Path) -> TokenCategory:
    text = path.read_text(encoding="utf-8")
    category_title = path.stem.replace("-", " ").title()
    groups: list[TokenGroup] = []
    current = TokenGroup()
    category_blurb: list[Block] = []
    seen_opening_comment = False
    previous_end = 0

    for match in _SCAN_RE.finditer(text):
        if (comment := match.group("comment")) is not None:
            # A comment on the same line as the declaration before it documents
            # that token; anything else opens a new group.
            if "\n" not in text[previous_end : match.start()] and current.tokens:
                last = current.tokens[-1]
                title, blurb = _clean_comment(comment)
                description = f"{title} {_flatten(blurb)}".strip()
                current.tokens[-1] = Token(last.name, last.value, description, last.reference, last.resolved)
            else:
                # The marker is UI, not prose: it's read off here and stripped
                # so it doesn't show up mid-sentence in the rendered blurb.
                deprecated = "@deprecated" in comment
                title, blurb = _clean_comment(_DEPRECATED_RE.sub(" ", comment))
                # The opening comment is the category's own blurb only when it
                # just restates the filename ("Colors"); files whose first
                # comment names a tier ("Border-Radius Primitives") keep it as a
                # group heading instead.
                if not seen_opening_comment and _slug(title) == _slug(category_title):
                    category_blurb = blurb
                else:
                    if current.title or current.tokens or current.blurb:
                        groups.append(current)
                    current = TokenGroup(title, blurb, deprecated=deprecated or "deprecated" in title.lower())
                seen_opening_comment = True
        else:
            value = " ".join(match.group("value").split())
            reference = ref.group(1) if (ref := _VAR_RE.match(value)) else ""
            current.tokens.append(Token(match.group("name"), value, reference=reference))
        previous_end = match.end()

    if current.title or current.tokens or current.blurb:
        groups.append(current)
    return TokenCategory(path.stem, category_title, category_blurb, groups)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _resolve(categories: list[TokenCategory]) -> None:
    """Fill in ``resolved`` by chasing ``var()`` aliases to a concrete value.

    Later definitions win, matching how the browser resolves a token that is
    declared more than once.
    """
    values = {token.name: token.value for category in categories for group in category.groups for token in group.tokens}

    def chase(name: str) -> str:
        seen = set()
        while name in values and name not in seen:
            seen.add(name)
            value = values[name]
            if not (match := _VAR_RE.match(value)):
                return value
            name = match.group(1)
        return ""

    for category in categories:
        for group in category.groups:
            group.tokens = [
                Token(token.name, token.value, token.description, token.reference, chase(token.reference) if token.reference else "") for token in group.tokens
            ]


def _drop_internal(categories: list[TokenCategory]) -> None:
    """Drop every tier marked ``@internal`` — its heading and the groups beneath it.

    Tier headings are the token-less groups, so one marker covers everything
    down to the next heading and the tokens themselves stay untouched in the
    CSS. Runs after ``_resolve`` so a dropped token can still be the end of an
    alias chain.
    """
    for category in categories:
        kept: list[TokenGroup] = []
        internal = False
        for group in category.groups:
            if not group.tokens:
                internal = _INTERNAL_MARKER in group.title
            if not internal:
                kept.append(group)
        category.groups = kept


@cache
def load_token_categories() -> list[TokenCategory]:
    """Every token category, ordered for reading rather than alphabetically.

    The barrel's ``@import`` list is the source of which files exist; the order
    below is what a reader wants — the categories they reach for daily first.
    Returns an empty list if the token files are unreadable so the rest of the
    design system page still renders.
    """
    try:
        names = _IMPORT_RE.findall(BARREL_PATH.read_text(encoding="utf-8"))
        categories = [_parse_file(TOKENS_DIR / f"{name}.css") for name in names]
    except OSError:
        return []
    _resolve(categories)
    _drop_internal(categories)
    categories.sort(key=lambda category: (_DISPLAY_ORDER.index(category.id) if category.id in _DISPLAY_ORDER else len(_DISPLAY_ORDER), category.id))
    return categories
