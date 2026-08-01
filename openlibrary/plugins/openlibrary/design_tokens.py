"""Parse the design-token CSS into a structure the design system page can render.

The token files already document themselves with block comments, so Foundations
reads that structure out of the CSS rather than repeating it.

Gotcha: parsed values are only ever *labels*. Previews render with
``var(--token)`` so the browser resolves what Python can't (``color-mix()``,
deep ``var()`` chains).
"""

import re
import textwrap
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

TOKENS_DIR = Path(__file__).parents[3] / "static" / "css" / "tokens"
BARREL_PATH = TOKENS_DIR.parent / "tokens.css"

# Comments come first in the alternation, so a declaration written inside a
# comment is consumed as prose rather than picked up as a token.
_SCAN_RE = re.compile(r"/\*(?P<comment>.*?)\*/|(?P<name>--[\w-]+)\s*:\s*(?P<value>[^;{}]+);", re.DOTALL)
_IMPORT_RE = re.compile(r"""@import\s+["']tokens/([\w-]+)\.css["']""")
_VAR_RE = re.compile(r"^var\(\s*(--[\w-]+)\s*\)$")
_RAMP_RE = re.compile(r"^(--[\w-]+?)-(\d+)$")
_DECORATION_RE = re.compile(r"^[\s*=~_-]+$")
_LIST_ITEM_RE = re.compile(r"^(?P<marker>[-*•]|\d+\.)\s+(?P<text>\S.*)$")
# A markdown pipe table, so a comment can carry a lookup table (colors.css).
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
_TABLE_RULE_RE = re.compile(r"^\|[\s|:-]+\|$")
# Markers are UI, not prose: read off the raw comment, then stripped.
_MARKER_RE = re.compile(r"\s*@(?:deprecated|internal)\b\s*")
# ASCII art (spacing.css) keeps its whitespace. Arrows are excluded on purpose:
# they show up in ordinary prose ("Blues → blue ramp").
_DIAGRAM_CHARS = set("┌┐└┘├┤┬┴┼─│")
# An indented run is an example or a table, not prose.
_PRE_INDENT = 2
_COLOR_PREFIXES = ("#", "hsl", "rgb", "color-mix", "oklch", "oklab", "lab", "lch")
_TITLE_SPLIT_LENGTH = 60
_MIN_RAMP_STEPS = 3
# Marks a tier as belonging to one component, not the shared vocabulary.
_INTERNAL_MARKER = "@internal"
# Reading order for the Foundations page. Anything not listed sorts to the end.
_DISPLAY_ORDER = ("colors", "font-families", "line-heights", "spacing", "border-radius", "borders", "control-heights", "z-index", "breakpoints")


@dataclass(frozen=True)
class Block:
    """One run of a comment body: a paragraph, a list, a table, or preformatted text.

    The comments are written for a reader, so the structure survives instead of
    flattening into one run-on paragraph.
    """

    kind: str
    text: str = ""
    items: tuple[str, ...] = ()
    ordered: bool = False
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class Token:
    """One custom property, with the trailing comment that documents it."""

    name: str
    value: str
    description: str = ""
    resolved: str = ""

    @property
    def reference(self) -> str:
        """The token this one aliases, when its whole value is a single ``var()``."""
        return match.group(1) if (match := _VAR_RE.match(self.value)) else ""

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

    No tokens means a standalone tier header; no title means a run introduced
    by prose alone.
    """

    title: str = ""
    blurb: list[Block] = field(default_factory=list)
    tokens: list[Token] = field(default_factory=list)
    deprecated: bool = False
    internal: bool = False

    @property
    def display_title(self) -> str:
        return re.sub(r"\s+", " ", self.title).strip()

    @property
    def ramps(self) -> list[tuple[str, list[Token]]]:
        """Every ``<prefix>-<number>`` color ramp of three or more steps.

        A list, not a verdict on the group: one group can hold several ramps and
        mix them with standalone tokens.
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


def _trim_blank(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


def _dedent(lines: list[str]) -> list[str]:
    """Make indentation relative: what matters is which lines are indented
    *further* than their neighbours, since that is what marks an example."""
    return textwrap.dedent("\n".join(lines)).split("\n")


def _table_block(rows: list[str]) -> Block:
    """A run of pipe rows as a table — or a paragraph, if it has no header rule.

    Without the rule the run is prose that happens to use pipes, and rendering
    it as a headed table would invent a heading it never had.
    """
    cells = [tuple(cell.strip() for cell in row.strip("|").split("|")) for row in rows if not _TABLE_RULE_RE.match(row)]
    if not cells or len(cells) == len(rows):
        return Block("paragraph", text=" ".join(rows))
    return Block("table", headers=cells[0], rows=tuple(cells[1:]))


def _blocks(lines: list[str]) -> list[Block]:
    """Group a dedented comment body into paragraphs, lists and preformatted runs.

    A blank line always ends a block. List continuations are indented, so the
    list case is checked before the indentation one.
    """
    blocks: list[Block] = []
    paragraph: list[str] = []
    pre: list[str] = []
    items: list[list[str]] = []
    table: list[str] = []
    ordered = False

    def flush() -> None:
        nonlocal paragraph, pre, items, table
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
        if table:
            blocks.append(_table_block(table))
            table = []

    for line in lines:
        stripped = line.strip()
        indented = len(line) - len(line.lstrip()) >= _PRE_INDENT
        if not stripped:
            flush()
        elif _TABLE_ROW_RE.match(stripped):
            if not table:
                flush()
            table.append(stripped)
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

    def one(block: Block) -> str:
        if block.kind == "list":
            return " ".join(block.items)
        if block.kind == "table":
            return " ".join(" ".join(row) for row in (block.headers, *block.rows))
        return block.text

    return " ".join(one(block) for block in blocks).strip()


def _clean_comment(raw: str) -> tuple[str, list[Block]]:
    """Split a block comment into a title and the blocks that make up its body.

    The first line is a heading only when it reads like one; otherwise it stays
    in the body, since a wrapped sentence promoted to a heading breaks mid-clause.
    """
    lines = _trim_blank([re.sub(r"^\s*\*[ \t]?", "", line).rstrip() for line in raw.split("\n")])
    if not lines:
        return "", []

    first, rest = lines[0], lines[1:]
    after = rest[0] if rest else ""
    # Dedent first, so a sentence pulled out of the heading below lines up with
    # the body rather than resetting its indentation.
    rest = _dedent(_trim_blank([line for line in rest if not _DECORATION_RE.match(line)]))

    # Leading dashes come from "---- Inline ----" headings; the trailing set is
    # the em and en dashes, spelled out so the literal is unambiguous.
    heading = first.strip().strip("-").strip().rstrip(" ,;:-\u2014\u2013")
    # Nothing after it, a blank line after it, or a rule under it: a heading.
    if not after or _DECORATION_RE.match(after):
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
            title, blurb = _clean_comment(_MARKER_RE.sub(" ", comment))
            if "\n" not in text[previous_end : match.start()] and current.tokens:
                description = f"{title} {_flatten(blurb)}".strip()
                current.tokens[-1] = replace(current.tokens[-1], description=description)
            else:
                # The opening comment is the category's blurb only when it
                # restates the filename; if it names a tier, it stays a heading.
                if not seen_opening_comment and _slug(title) == _slug(category_title):
                    category_blurb = blurb
                else:
                    if current.title or current.tokens or current.blurb:
                        groups.append(current)
                    current = TokenGroup(
                        title,
                        blurb,
                        deprecated="@deprecated" in comment or "deprecated" in title.lower(),
                        internal=_INTERNAL_MARKER in comment,
                    )
                seen_opening_comment = True
        else:
            current.tokens.append(Token(match.group("name"), " ".join(match.group("value").split())))
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
            group.tokens = [replace(token, resolved=chase(token.reference) if token.reference else "") for token in group.tokens]


def _drop_internal(categories: list[TokenCategory]) -> None:
    """Drop every group marked ``@internal``, and any tier marked that way.

    Runs after ``_resolve`` so a dropped token can still end an alias chain.
    """
    for category in categories:
        kept: list[TokenGroup] = []
        internal = False
        for group in category.groups:
            # A tier heading opens or closes the run; a marked group with
            # tokens of its own drops just itself.
            if not group.tokens:
                internal = group.internal
            if not (internal or group.internal):
                kept.append(group)
        category.groups = kept


@cache
def load_token_categories() -> list[TokenCategory]:
    """Every token category, ordered for reading rather than alphabetically.

    The barrel's ``@import`` list says which files exist. Returns empty if they
    can't be read, so the rest of the page still renders.
    """
    try:
        names = _IMPORT_RE.findall(BARREL_PATH.read_text(encoding="utf-8"))
        categories = [_parse_file(TOKENS_DIR / f"{name}.css") for name in names]
    except OSError:
        return []
    _resolve(categories)
    _drop_internal(categories)

    def rank(category: TokenCategory) -> tuple[int, int]:
        """Listed categories in reading order, then the rest in barrel order, so
        forgetting ``_DISPLAY_ORDER`` costs position rather than sense."""
        if category.id in _DISPLAY_ORDER:
            return (0, _DISPLAY_ORDER.index(category.id))
        return (1, names.index(category.id))

    categories.sort(key=rank)
    return categories
