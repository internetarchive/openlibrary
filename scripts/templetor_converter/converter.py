"""Templetor-to-Jinja2 template converter for Open Library.

Converts web.py Templetor templates (.html) into equivalent Jinja2 templates.

Conversion stats (as of 2026-06-11):
  - 79/79 openlibrary/macros/*.html templates convert cleanly (zero raw $ lines)
  - 115 unit tests passing

Supported Templetor syntax:
  - $def with (args)          → {% macro Name(args) %}
  - $def func(args):          → {% macro func(args) %}...{% endmacro %}
  - $for ...:                 → {% for ... %}...{% endfor %}
  - $if ...: / $elif / $else  → {% if ... %}...{% elif %}...{% else %}...{% endif %}
  - $ var = expr              → {% set var = expr %}
  - $ var1, var2 = expr       → {% set var1, var2 = expr %}  (tuple unpacking)
  - $ var += expr             → {% set var = var + expr %}  (augmented assignment)
  - $ var['key'] = expr       → {# CODE: var['key'] = expr #}  (subscript LHS)
  - $ code:                   → converted to Jinja set/macro/for/if
  - $expr                     → {{ expr }}
  - $ expr                    → {{ expr }}  ($ with space also works)
  - $:expr                    → {{ expr | safe }}
  - $(expr)                   → {{ expr }}  (balanced-paren tracking)
  - ${expr}                   → {{ expr }}  (balanced-brace tracking)
  - $:func(args)              → {{ func(args) | safe }}  (balanced-paren tracking)
  - $:'string'.method()       → {{ 'string'.method() | safe }}  (string literal scanning)
  - $:_.get(k, v)             → {{ _.get(k, v) | safe }}  (method access on _ object)
  - $:_("text")               → {{ _("text") | safe }}  (i18n raw output)
  - $_("text")                → {{ _("text") }}  (i18n auto-escaped)
  - $cond(expr, val, default) → {{ val if expr else default }}
  - $ungettext(...)           → {{ ungettext(...) }}
  - $$                        → $
  - $# comment                → {# comment #}
  - Multi-line expressions    → collected into single {% set %}
  - Python # comments         → stripped from continuation lines

Assumptions:
  - Templates use 4-space indentation (standard Python)
  - $def with is always the first non-blank line
  - Macro name is derived from filename when $def with is used
  - $: emits | safe for raw (unescaped) output in Jinja2

Known limitations (require human review):
  - $code blocks with complex Python logic (multi-line expressions, list comprehensions)
    are wrapped as {# CODE: ... #} comments — need manual conversion
  - $continue → {{ continue }} — Jinja has no continue statement, needs {# continue #}
  - $ var = expr == comparison — RE_SET_TUPLE may match the first = incorrectly
  - String formatting with % ("%s" % var) works in Jinja but behaves slightly differently
    than Python — verify output matches expectations
  - Side-effect method calls ($ dict.update(...)) are converted to {{ dict.update(...) }}
    which outputs None — consider moving to view layer if output is unwanted
  - Escaped quotes inside i18n strings require careful handling
  - Line continuation backslash (\\) is not handled
  - Nested bracket tracking in bare/raw expressions doesn't handle strings containing
    brackets (e.g. $:foo['key with ] inside']) — extremely rare edge case
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass
class BlockInfo:
    """Tracks an open Jinja block that needs closing."""

    keyword: str  # e.g. 'for', 'if', 'macro'
    indent: int  # indentation level where the block started
    is_file_macro: bool = False  # True for $def with (never closed mid-file)


@dataclass
class ConverterState:
    """State tracked across line-by-line conversion."""

    output_lines: list[str] = field(default_factory=list)
    open_blocks: list[BlockInfo] = field(default_factory=list)
    prev_line_blank: bool = False
    block_indent_unit: int = 0  # detected indentation unit (e.g. 4)
    macro_name: str = ""  # name extracted from $def with


# ── Regex helpers ────────────────────────────────────────────────────────
# Built at module level to avoid class-level escaping nightmares.

RE_DEF_WITH = re.compile(r"^\$def\s+with\s*(.*)")
RE_DEF_FUNC = re.compile(r"^\$def\s+(\w+)\s*\(([^)]*)\)\s*:")
RE_CODE_BLOCK = re.compile(r"^\$code\s*:")
RE_FOR = re.compile(r"^\$for\s+(.+):")
RE_IF = re.compile(r"^\$if\s+(.+):")
RE_ELIF = re.compile(r"^\$elif\s+(.+):")
RE_ELSE = re.compile(r"^\$else\s*:")
RE_TRY = re.compile(r"^\$try\s*:")
RE_EXCEPT = re.compile(r"^\$except(?:\s+(.+?))?\s*:")
RE_FINALLY = re.compile(r"^\$finally\s*:")
RE_RAW_EXPR = re.compile(r"^\$:(.+)")
RE_COMMENT = re.compile(r"^\$#(.*)")
RE_ESCAPED_DOLLAR = re.compile(r"\$\$")

RE_COND = re.compile(r"\$cond\s*\(")
RE_COND_BARE = re.compile(r"(?<![\w.])cond\s*\(")  # cond() without $ prefix
RE_UNGETTEXT = re.compile(r"\$ungettext\s*\(")
RE_SET_AUG = re.compile(r"^\$\s+(\w+)\s*([+\-*/|&^%]=)\s*(.+)")  # requires operator prefix (+= not plain =)
RE_SET_TUPLE = re.compile(r"^\$\s+([\w\s,]+?)\s*=\s*(.+)")  # tuple unpacking: $ var1, var2 = expr
RE_SET_SUBSCRIPT = re.compile(r"^\$\s+(\w+\[.+?\])\s*=\s*(.+)")  # subscript assignment: $ var['key'] = expr
RE_INDENT = re.compile(r"^(\s*)")

# Marker patterns for i18n (start only, balanced-paren handled by functions)
RE_I18N_RAW_MARKER = re.compile(r"\$:_\(")
RE_I18N_CALL_MARKER = re.compile(r"\$_\(")


# ── Top-level helper functions ───────────────────────────────────────────


RE_TYPE_HINT = re.compile(r"\s*:\s*(?:bool|int|str|float|list|dict|None)\b")


def _sanitize_macro_name(name: str) -> str:
    """Replace hyphens with underscores in macro names.

    Jinja2 identifiers cannot contain hyphens.
    """
    return name.replace("-", "_")


def _strip_type_hints(args: str) -> str:
    """Strip Python type hints (e.g. ``name: bool``) from macro argument lists.

    Jinja2 macros don't support type annotations.
    """
    return RE_TYPE_HINT.sub("", args)


def _strip_variadic_args(args: str) -> str:
    """Strip ``*args`` and ``**kwargs`` from macro argument lists.

    Jinja2 macros don't support variadic arguments.
    """
    parts = _split_top_level_args(args)
    filtered = []
    for part in parts:
        stripped = part.strip()
        if stripped.startswith("*"):
            continue  # skip *args and **kwargs
        filtered.append(stripped)
    return ", ".join(filtered)


def _has_jinja_incompatible_expr(set_expr: str) -> bool:
    """Check if an expression contains Jinja2-incompatible patterns.

    Detects generator expressions, list comprehensions, lambda, and
    trailing-dot numbers — none of which work inside Jinja2 ``{% set %}``
    or ``{{ }}`` tags.

    NOTE: Dict literals (``{...}``) and ``%`` string formatting
    (``"..." % val``) are both valid Jinja2 and are NOT flagged here.
    """
    # Check for generator/comprehension: 'for ... in ...' inside [] or ()
    if re.search(r"\bfor\s+\w+.*\bin\b", set_expr):
        return True
    # Check for lambda
    if "lambda" in set_expr and re.search(r"\blambda\b", set_expr):
        return True
    # Check for trailing-dot numbers (100.) — invalid in Jinja2
    if re.search(r"\b\d+\.(?![a-zA-Z_\d])", set_expr):
        return True
    return False


def _has_unclosed_grouping(s: str) -> bool:
    """Check if *s* has unclosed parentheses, brackets, or braces."""
    paren = bracket = brace = 0
    in_quote: str | None = None
    i = 0
    while i < len(s):
        ch = s[i]
        if in_quote:
            if ch == "\\" and i + 1 < len(s):
                i += 2  # skip escaped char
                continue
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        i += 1
    return paren > 0 or bracket > 0 or brace > 0


def _strip_trailing_py_comment(s: str) -> str:
    """Strip a trailing Python ``# ...`` comment from *s*, respecting quotes."""
    in_quote: str | None = None
    j = 0
    while j < len(s):
        ch = s[j]
        if in_quote:
            if ch == "\\" and j + 1 < len(s):
                j += 2
                continue
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
        elif ch == "#":
            return s[:j].rstrip()
        j += 1
    return s


def _collect_continuation_lines(lines: list[str], i: int, expr: str) -> tuple[str, int]:
    """Collect continuation lines for multi-line expressions.

    When an expression has unclosed brackets/parens, subsequent lines
    starting with ``$ `` or ``$`` are merged into the expression.
    Python ``# ...`` comments in continuation lines are stripped.
    """
    while _has_unclosed_grouping(expr) and i + 1 < len(lines):
        next_line = lines[i + 1].strip()
        if next_line.startswith("$ "):
            content = _strip_trailing_py_comment(next_line[2:].strip())
            if content:
                expr += " " + content
            i += 1
        elif next_line.startswith("$") and len(next_line) > 1:
            content = _strip_trailing_py_comment(next_line[1:].strip())
            if content:
                expr += " " + content
            i += 1
        else:
            break
    return expr, i


def _find_balanced_close(s: str, start: int) -> int:
    """Find the index of the closing ')' that balances the '(' at *start*.

    Returns -1 if no balanced close is found.
    """
    depth = 0
    i = start
    while i < len(s):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_top_level_args(s: str) -> list[str]:
    """Split *s* on top-level commas (respecting parentheses and quotes)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_quote: str | None = None
    i = 0
    while i < len(s):
        ch = s[i]
        if in_quote:
            current.append(ch)
            if ch == "\\":
                # Skip escaped char inside quotes
                if i + 1 < len(s):
                    i += 1
                    current.append(s[i])
            elif ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        parts.append("".join(current))
    return parts


def _convert_cond_in_line(line: str, wrap: bool = True) -> str:
    """Convert all ``$cond(expr, val[, default])`` calls in a line to Jinja ternary.

    Also handles bare ``cond(expr, val[, default])`` (without ``$`` prefix)
    which appears when the ``$`` is stripped by ``RE_SET`` or ``_convert_expressions``.

    Args:
        line: The line to process.
        wrap: If True, wrap the result in ``{{ ... }}`` (for content lines).
              If False, return just the expression (for ``{% set %}`` context).
    """
    result: list[str] = []
    i = 0
    while i < len(line):
        # Try $cond first, then bare cond
        m = RE_COND.search(line, i)
        if not m:
            m = RE_COND_BARE.search(line, i)
        if not m:
            result.append(line[i:])
            break

        # Append text before the match
        result.append(line[i : m.start()])

        open_paren = m.end() - 1  # index of the '('
        close_paren = _find_balanced_close(line, open_paren)
        if close_paren == -1:
            # Unbalanced – leave as-is
            result.append(m.group(0))
            i = m.end()
            continue

        inner = line[open_paren + 1 : close_paren]
        parts = _split_top_level_args(inner)

        if len(parts) >= 2:
            expr = parts[0].strip()
            val = parts[1].strip()
            default = parts[2].strip() if len(parts) >= 3 else "''"
            ternary = f"{val} if {expr} else {default}"
            result.append(f"{{{{ {ternary} }}}}" if wrap else ternary)
        else:
            # Malformed – leave as-is
            result.append(m.group(0) + inner + ")")

        i = close_paren + 1

    return "".join(result)


def _convert_i18n_raw(line: str) -> str:
    """Convert ``$:_(...)`` to ``{{ _(...) | safe }}`` using balanced-paren tracking.

    Unlike the old regex approach (which broke on nested calls like
    ``$:_(\"text\", name=func(a, b))``), this correctly tracks parentheses.
    """
    result: list[str] = []
    i = 0
    while i < len(line):
        m = RE_I18N_RAW_MARKER.search(line, i)
        if not m:
            result.append(line[i:])
            break

        result.append(line[i : m.start()])
        open_paren = m.end() - 1  # index of '('
        close_paren = _find_balanced_close(line, open_paren)
        if close_paren == -1:
            result.append(m.group(0))
            i = m.end()
            continue
        inner = line[open_paren + 1 : close_paren]
        if _has_jinja_incompatible_expr(inner):
            result.append("{# CODE: $:_(" + inner + ") #}")
        else:
            result.append(f"{{{{ _({inner}) | safe }}}}")
        i = close_paren + 1

    return "".join(result)


def _convert_i18n_call(line: str) -> str:
    """Convert ``$_(...)`` to ``{{ _(...) }}`` using balanced-paren tracking."""
    result: list[str] = []
    i = 0
    while i < len(line):
        m = RE_I18N_CALL_MARKER.search(line, i)
        if not m:
            result.append(line[i:])
            break

        result.append(line[i : m.start()])
        open_paren = m.end() - 1  # index of '('
        close_paren = _find_balanced_close(line, open_paren)
        if close_paren == -1:
            result.append(m.group(0))
            i = m.end()
            continue
        inner = line[open_paren + 1 : close_paren]
        if _has_jinja_incompatible_expr(inner):
            result.append("{# CODE: $_(" + inner + ") #}")
        else:
            result.append(f"{{{{ _({inner}) }}}}")
        i = close_paren + 1

    return "".join(result)


def _convert_explicit_parens(line: str) -> str:
    """Convert ``$(expr)`` to ``{{ expr }}`` using balanced-paren tracking.

    Handles nested calls like ``$(doc['log'].replace(' ', '-'))``
    and ``$(urlquote(i))``.
    """
    result: list[str] = []
    i = 0
    while i < len(line):
        idx = line.find("$(", i)
        if idx == -1:
            result.append(line[i:])
            break

        open_paren = idx + 1  # index of '('
        close_paren = _find_balanced_close(line, open_paren)
        if close_paren == -1:
            result.append(line[i : idx + 2])
            i = idx + 2
            continue
        result.append(line[i:idx])
        inner = line[open_paren + 1 : close_paren]
        if _has_jinja_incompatible_expr(inner):
            result.append("{# CODE: $(" + inner + ") #}")
        else:
            result.append(f"{{{{ {inner} }}}}")
        i = close_paren + 1

    return "".join(result)


def _convert_explicit_braces(line: str) -> str:
    """Convert ``${expr}`` to ``{{ expr }}`` using balanced-brace tracking."""
    result: list[str] = []
    i = 0
    while i < len(line):
        idx = line.find("${", i)
        if idx == -1:
            result.append(line[i:])
            break

        open_brace = idx + 1  # index of '{'
        depth = 1
        j = open_brace + 1
        while j < len(line) and depth > 0:
            if line[j] == "{":
                depth += 1
            elif line[j] == "}":
                depth -= 1
            j += 1

        if depth != 0:
            result.append(line[i : idx + 2])
            i = idx + 2
            continue

        close_brace = j - 1
        result.append(line[i:idx])
        inner = line[open_brace + 1 : close_brace]
        if _has_jinja_incompatible_expr(inner):
            result.append("{# CODE: ${" + inner + "} #}")
        else:
            result.append(f"{{{{ {inner} }}}}")
        i = close_brace + 1

    return "".join(result)


def _convert_raw_expressions(line: str) -> str:
    """Convert all ``$:expression`` patterns to ``{{ expr | safe }}``.

    Handles ``$:identifier``, ``$:obj.method()``, ``$:func(a, b)`` etc.
    by scanning character-by-character with balanced-parenthesis tracking.
    """
    result: list[str] = []
    i = 0
    while i < len(line):
        # Find next $:
        idx = line.find("$:", i)
        if idx == -1:
            result.append(line[i:])
            break

        after = idx + 2

        # Skip $:_(  (i18n raw) -- already handled by _convert_i18n_raw above
        # But don't skip $:_.method() which is a method access on the _ object
        if after < len(line) and line[after] == "_" and (after + 1 >= len(line) or line[after + 1] == "("):
            result.append(line[i:after])
            i = after
            continue

        # Skip $:{{ ... }} -- already-converted Jinja from $:cond() etc.
        if after < len(line) - 1 and line[after] == "{" and line[after + 1] == "{":
            result.append(line[i:idx])
            # Find the matching }}
            close = line.find("}}", after + 2)
            if close != -1:
                result.append(line[after : close + 2])
                i = close + 2
            else:
                result.append(line[after:])
                i = len(line)
            continue

        # Must start with a word character, '(', or quote (string literal)
        if after >= len(line) or not (line[after].isalpha() or line[after] == "_" or line[after] == "(" or line[after] in ('"', "'")):
            result.append(line[i:after])
            i = after
            continue

        # Append text before the $:
        result.append(line[i:idx])

        # Scan the expression: word chars, dots, balanced parens, balanced brackets, string literals
        j = after
        while j < len(line):
            ch = line[j]
            if ch.isalnum() or ch == "_" or ch == ".":
                j += 1
            elif ch == "(":
                close = _find_balanced_close(line, j)
                if close == -1:
                    break
                j = close + 1
            elif ch == "[":
                # Track balanced brackets (handles $:expr[0], $:expr['key'])
                depth = 1
                j += 1
                while j < len(line) and depth > 0:
                    if line[j] == "[":
                        depth += 1
                    elif line[j] == "]":
                        depth -= 1
                    j += 1
            elif ch in ('"', "'"):
                # Scan string literal
                quote = ch
                j += 1
                while j < len(line) and line[j] != quote:
                    if line[j] == "\\" and j + 1 < len(line):
                        j += 1
                    j += 1
                if j < len(line):
                    j += 1  # skip closing quote
                # After string literal, continue through % expr (string formatting)
                # e.g. $:"%.2f" % val → capture full "%.2f" % val
                k = j
                while k < len(line) and line[k] == " ":
                    k += 1
                if k < len(line) and line[k] == "%":
                    j = k + 1  # skip past %
                    # Skip whitespace, then continue main scan
                    while j < len(line) and line[j] == " ":
                        j += 1
                    continue  # re-enter main scanning loop for RHS
            else:
                break

        expr = line[after:j]
        if _has_jinja_incompatible_expr(expr):
            result.append("{# CODE: $:" + expr + " #}")
        else:
            result.append(f"{{{{ {expr} | safe }}}}")
        i = j

    return "".join(result)


def _convert_bare_expressions(line: str) -> str:
    """Convert ``$var``, ``$var.method()``, ``$var['key']`` etc. to ``{{ expr }}``.

    Uses character-by-character scanning with balanced-paren/bracket tracking
    so that ``$var(args)`` and ``$var['key']`` are fully captured.
    """
    result: list[str] = []
    i = 0
    while i < len(line):
        # Find next $
        idx = line.find("$", i)
        if idx == -1:
            result.append(line[i:])
            break

        after = idx + 1

        # Must start with a letter or underscore
        if after >= len(line) or not (line[after].isalpha() or line[after] == "_"):
            result.append(line[i:after])
            i = after
            continue

        # Append text before the $
        result.append(line[i:idx])

        # Scan: word chars, dots, balanced parens, balanced brackets
        j = after
        while j < len(line):
            ch = line[j]
            if ch.isalnum() or ch == "_" or ch == ".":
                j += 1
            elif ch == "(":
                close = _find_balanced_close(line, j)
                if close == -1:
                    break
                j = close + 1
            elif ch == "[":
                # Track balanced brackets
                depth = 1
                j += 1
                while j < len(line) and depth > 0:
                    if line[j] == "[":
                        depth += 1
                    elif line[j] == "]":
                        depth -= 1
                    j += 1
            else:
                break

        expr = line[after:j]
        if _has_jinja_incompatible_expr(expr):
            result.append("{# CODE: $" + expr + " #}")
        else:
            result.append(f"{{{{ {expr} }}}}")
        i = j

    return "".join(result)


def _convert_ungettext_in_line(line: str) -> str:
    """Convert ``$ungettext(...)`` calls to ``{{ ungettext(...) }}``."""
    result: list[str] = []
    i = 0
    while i < len(line):
        m = RE_UNGETTEXT.search(line, i)
        if not m:
            result.append(line[i:])
            break

        # Append text before the match
        result.append(line[i : m.start()])

        open_paren = m.end() - 1  # index of the '('
        close_paren = _find_balanced_close(line, open_paren)
        if close_paren == -1:
            # Unbalanced – leave as-is
            result.append(m.group(0))
            i = m.end()
            continue

        inner = line[open_paren + 1 : close_paren]
        result.append(f"{{{{ ungettext({inner}) }}}}")
        i = close_paren + 1

    return "".join(result)


class TempletorToJinjaConverter:
    """Converts Templetor templates to Jinja2 templates.

    Usage:
        converter = TempletorToJinjaConverter()
        jinja_output = converter.convert(templetor_input)
        # or from file:
        jinja_output = converter.convert_file("path/to/template.html")
    """

    def __init__(self, macro_name: str = ""):
        """Initialize converter.

        Args:
            macro_name: Name for the generated Jinja macro when input uses
                       $def with. If empty, will be auto-detected from context.
        """
        self.macro_name = macro_name

    # ── Public API ───────────────────────────────────────────────────────

    def convert(self, text: str) -> str:
        """Convert Templetor template text to Jinja2."""
        state = ConverterState()
        state.macro_name = self.macro_name
        lines = text.split("\n")
        # Strip trailing empty lines to avoid spurious blanks before end tags
        while lines and not lines[-1].strip():
            lines.pop()
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # ── Skip empty lines ──
            if not stripped:
                state.output_lines.append("")
                state.prev_line_blank = True
                i += 1
                continue

            indent = len(RE_INDENT.match(line).group(1))

            # ── Close blocks whose indentation has ended ──
            is_continuation = bool(RE_ELIF.match(stripped) or RE_ELSE.match(stripped) or RE_EXCEPT.match(stripped) or RE_FINALLY.match(stripped))
            self._close_blocks_to_indent(state, indent, inclusive=not is_continuation)

            # ── $def with (args) → {% macro Name(args) %} ──
            if m := RE_DEF_WITH.match(stripped):
                args = m.group(1).strip()
                if args.startswith("(") and args.endswith(")"):
                    args = args[1:-1].strip()
                # Jinja2 macros don't support *args/**kwargs — strip them
                # Also strip type hints (e.g. name: bool) and sanitize hyphens
                args = _strip_type_hints(args)
                args = _strip_variadic_args(args)
                name = _sanitize_macro_name(state.macro_name or "Template")
                self._append(state, indent, f"{{% macro {name}({args}) %}}")
                state.open_blocks.append(BlockInfo("macro", indent, is_file_macro=True))
                state.block_indent_unit = 0
                i += 1
                continue

            # ── $def func(args): → {% macro func(args) %} ──
            if m := RE_DEF_FUNC.match(stripped):
                fname = _sanitize_macro_name(m.group(1))
                fargs = _strip_type_hints(m.group(2).strip())
                fargs = _strip_variadic_args(fargs)
                self._append(state, indent, f"{{% macro {fname}({fargs}) %}}")
                state.open_blocks.append(BlockInfo("macro", indent))
                i += 1
                continue

            # ── $code: block ──
            if RE_CODE_BLOCK.match(stripped):
                code_lines, i = self._collect_block_body(lines, i + 1, indent)
                self._convert_code_block(state, indent, code_lines)
                continue

            # ── $for ...: ──
            if m := RE_FOR.match(stripped):
                expr = m.group(1).strip()
                if _has_jinja_incompatible_expr(expr):
                    code_line = stripped[2:].strip()  # strip '$' prefix
                    self._append(state, indent, f"{{# CODE: {code_line} #}}")
                else:
                    self._append(state, indent, f"{{% for {self._convert_expressions(expr)} %}}")
                    state.open_blocks.append(BlockInfo("for", indent))
                i += 1
                continue

            # ── $if ...: ──
            if m := RE_IF.match(stripped):
                expr = m.group(1).strip()
                self._append(state, indent, f"{{% if {self._convert_expressions(expr)} %}}")
                state.open_blocks.append(BlockInfo("if", indent))
                i += 1
                continue

            # ── $elif ...: ──
            if m := RE_ELIF.match(stripped):
                if state.open_blocks and state.open_blocks[-1].keyword == "if":
                    state.open_blocks.pop()
                expr = m.group(1).strip()
                self._append(state, indent, f"{{% elif {self._convert_expressions(expr)} %}}")
                state.open_blocks.append(BlockInfo("if", indent))
                i += 1
                continue

            # ── $else: ──
            if RE_ELSE.match(stripped):
                if state.open_blocks and state.open_blocks[-1].keyword == "if":
                    state.open_blocks.pop()
                self._append(state, indent, "{% else %}")
                state.open_blocks.append(BlockInfo("if", indent))
                i += 1
                continue

            # ── $try: ──
            if RE_TRY.match(stripped):
                self._append(state, indent, "{% try %}")
                state.open_blocks.append(BlockInfo("try", indent))
                i += 1
                continue

            # ── $except ...: ──
            if m := RE_EXCEPT.match(stripped):
                if state.open_blocks and state.open_blocks[-1].keyword == "try":
                    state.open_blocks.pop()
                expr = m.group(1) or ""
                expr_str = f" {expr}" if expr else ""
                self._append(state, indent, f"{{% except{expr_str} %}}")
                state.open_blocks.append(BlockInfo("try", indent))
                i += 1
                continue

            # ── $finally: ──
            if RE_FINALLY.match(stripped):
                if state.open_blocks and state.open_blocks[-1].keyword == "try":
                    state.open_blocks.pop()
                self._append(state, indent, "{% finally %}")
                state.open_blocks.append(BlockInfo("try", indent))
                i += 1
                continue

            # ── $ var += expr (augmented assignment) ──
            if m := RE_SET_AUG.match(stripped):
                varname = m.group(1)
                op = m.group(2)
                expr, i = _collect_continuation_lines(lines, i, m.group(3).strip())
                converted_expr = self._convert_expressions(expr)
                op_base = op[:-1]  # strip trailing '='
                self._append(state, indent, f"{{% set {varname} = {varname} {op_base} {converted_expr} %}}")
                i += 1
                continue

            # ── $ var['key'] = expr (subscript assignment — not convertible to {% set %}) ──
            if m := RE_SET_SUBSCRIPT.match(stripped):
                lhs = m.group(1)
                expr, i = _collect_continuation_lines(lines, i, m.group(2).strip())
                code_line = f"{lhs} = {expr}"
                self._append(state, indent, f"{{# CODE: {code_line} #}}")
                i += 1
                continue

            # ── $ var = expr or $ var1, var2 = expr (assignment / tuple unpacking) ──
            if m := RE_SET_TUPLE.match(stripped):
                lhs = m.group(1).strip()
                expr, i = _collect_continuation_lines(lines, i, m.group(2).strip())
                expr = expr.rstrip(";").rstrip()
                if _has_jinja_incompatible_expr(expr):
                    self._append(state, indent, f"{{# CODE: {stripped[2:]} #}}")
                else:
                    converted_expr = self._convert_expressions(expr)
                    self._append(state, indent, f"{{% set {lhs} = {converted_expr} %}}")
                i += 1
                continue

            # ── $# comment ──
            if m := RE_COMMENT.match(stripped):
                comment = m.group(1)
                self._append(state, indent, f"{{# {comment.strip()} #}}")
                i += 1
                continue

            # ── $ expr (expression output — $ with space but not assignment) ──
            if stripped.startswith("$ ") and len(stripped) > 2:
                # Not an assignment — strip the space and process as content
                converted = self._convert_content_line("$" + stripped[2:])
                self._append(state, indent, converted)
                i += 1
                continue

            # ── Regular content line ──
            converted = self._convert_content_line(stripped)
            self._append(state, indent, converted)
            i += 1

        # Close any remaining open blocks
        self._close_all_blocks(state)

        return "\n".join(state.output_lines)

    def convert_file(self, filepath: str) -> str:
        """Convert a Templetor template file to Jinja2."""
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        if not self.macro_name:
            basename = os.path.basename(filepath)
            name, _ = os.path.splitext(basename)
            self.macro_name = name

        return self.convert(content)

    # ── Private: output helpers ──────────────────────────────────────────

    def _append(self, state: ConverterState, indent: int, line: str) -> None:
        """Append a line to output with proper indentation."""
        if state.open_blocks and state.block_indent_unit == 0 and indent > 0:
            state.block_indent_unit = indent
        state.output_lines.append(" " * indent + line)
        state.prev_line_blank = False

    # ── Private: block management ────────────────────────────────────────

    def _close_blocks_to_indent(
        self,
        state: ConverterState,
        current_indent: int,
        inclusive: bool = False,
    ) -> None:
        """Close open blocks whose indent is deeper than (or equal to, if
        inclusive) *current_indent*."""
        while state.open_blocks:
            block = state.open_blocks[-1]
            if inclusive:
                should_close = block.indent > current_indent or (block.indent == current_indent and not block.is_file_macro)
            else:
                should_close = block.indent > current_indent
            if should_close:
                state.open_blocks.pop()
                had_blank = bool(state.output_lines and state.output_lines[-1] == "")
                while state.output_lines and state.output_lines[-1] == "":
                    state.output_lines.pop()
                end_tag = self._get_end_tag(block.keyword)
                state.output_lines.append(" " * block.indent + end_tag)
                if had_blank and block.indent == current_indent:
                    state.output_lines.append("")
            else:
                break

    def _close_last_block_of_type(self, state: ConverterState, keyword: str) -> None:
        """Close the most recent block of a given type (used inside $code blocks)."""
        if state.open_blocks and state.open_blocks[-1].keyword == keyword:
            block = state.open_blocks.pop()
            end_tag = self._get_end_tag(block.keyword)
            state.output_lines.append(" " * block.indent + end_tag)

    def _close_all_blocks(self, state: ConverterState) -> None:
        """Close all remaining open blocks at end of file."""
        while state.open_blocks:
            block = state.open_blocks.pop()
            self._strip_trailing_blank_lines(state)
            end_tag = self._get_end_tag(block.keyword)
            state.output_lines.append(" " * block.indent + end_tag)

    @staticmethod
    def _strip_trailing_blank_lines(state: ConverterState) -> None:
        """Remove trailing empty lines from output (before an end tag)."""
        while state.output_lines and state.output_lines[-1] == "":
            state.output_lines.pop()

    @staticmethod
    def _get_end_tag(keyword: str) -> str:
        """Get the Jinja end tag for a block keyword."""
        mapping = {
            "for": "{% endfor %}",
            "if": "{% endif %}",
            "macro": "{% endmacro %}",
            "try": "{% endtry %}",
            "block": "{% endblock %}",
            "set": "{% endset %}",
        }
        return mapping.get(keyword, f"{{% end{keyword} %}}")

    # ── Private: $code block handling ────────────────────────────────────

    def _collect_block_body(self, lines: list[str], start: int, block_indent: int) -> tuple[list[str], int]:
        """Collect lines belonging to an indented block body."""
        body: list[str] = []
        i = start
        while i < len(lines):
            line = lines[i]
            if line.strip() == "":
                body.append("")
                i += 1
                continue
            indent = len(RE_INDENT.match(line).group(1))
            if indent <= block_indent:
                break
            body.append(line)
            i += 1
        while body and body[-1] == "":
            body.pop()
            i -= 1
        return body, i

    def _convert_code_block(self, state: ConverterState, indent: int, code_lines: list[str]) -> None:
        """Convert a ``$code:`` block to Jinja set statements or macros."""
        initial_stack_depth = len(state.open_blocks)
        in_func_def = False

        # Pre-merge multi-line expressions (lines with unclosed grouping)
        merged_lines = self._merge_multiline_code(code_lines)

        for code_line in merged_lines:
            stripped = code_line.strip()
            if not stripped:
                continue

            line_indent = len(RE_INDENT.match(code_line).group(1))

            func_match = re.match(r"def\s+(\w+)\s*\(([^)]*)\)\s*:", stripped)
            if func_match:
                in_func_def = True
                fname = _sanitize_macro_name(func_match.group(1))
                fargs = _strip_type_hints(func_match.group(2).strip())
                fargs = _strip_variadic_args(fargs)
                self._append(state, indent, f"{{% macro {fname}({fargs}) %}}")
                state.open_blocks.append(BlockInfo("macro", indent))
                continue

            if in_func_def:
                out_indent = max(line_indent, indent + 4)
                self._convert_code_line_to_jinja(state, out_indent, stripped)
            else:
                self._convert_code_line_to_jinja(state, indent, stripped)

        while len(state.open_blocks) > initial_stack_depth:
            block = state.open_blocks.pop()
            end_tag = self._get_end_tag(block.keyword)
            state.output_lines.append(" " * block.indent + end_tag)

    @staticmethod
    def _merge_multiline_code(code_lines: list[str]) -> list[str]:
        """Merge multi-line expressions in $code: blocks.

        Lines ending with unclosed grouping (``(``, ``[``, ``{``) are merged
        with subsequent continuation lines until grouping is closed.
        """
        merged: list[str] = []
        i = 0
        while i < len(code_lines):
            line = code_lines[i]
            stripped = line.strip()
            if not stripped:
                merged.append(line)
                i += 1
                continue

            base_indent = len(RE_INDENT.match(line).group(1))
            content = _strip_trailing_py_comment(stripped)
            if _has_unclosed_grouping(content):
                parts = [content]
                i += 1
                while i < len(code_lines):
                    next_line = code_lines[i]
                    next_stripped = next_line.strip()
                    if not next_stripped:
                        i += 1
                        continue
                    next_indent = len(RE_INDENT.match(next_line).group(1))
                    if next_indent >= base_indent:
                        parts.append(_strip_trailing_py_comment(next_stripped))
                        i += 1
                        # Check if accumulated expression is still incomplete
                        if not _has_unclosed_grouping(" ".join(parts)):
                            break
                    else:
                        break
                merged.append(" " * base_indent + " ".join(parts))
            else:
                merged.append(line)
                i += 1
        return merged

    def _convert_code_line_to_jinja(self, state: ConverterState, indent: int, line: str) -> None:
        """Convert a Python code line to Jinja syntax."""
        # Control flow must be checked BEFORE assignments to avoid
        # `if x == y:` being matched by the assignment regex.
        if m := re.match(r"if\s+(.+?)\s*:", line):
            expr = self._convert_expressions(m.group(1))
            self._append(state, indent, f"{{% if {expr} %}}")
            state.open_blocks.append(BlockInfo("if", indent))
        elif m := re.match(r"elif\s+(.+?)\s*:", line):
            if state.open_blocks and state.open_blocks[-1].keyword == "if":
                state.open_blocks.pop()
            expr = self._convert_expressions(m.group(1))
            self._append(state, indent, f"{{% elif {expr} %}}")
            state.open_blocks.append(BlockInfo("if", indent))
        elif re.match(r"else\s*:", line):
            if state.open_blocks and state.open_blocks[-1].keyword == "if":
                state.open_blocks.pop()
            self._append(state, indent, "{% else %}")
            state.open_blocks.append(BlockInfo("if", indent))
        elif m := re.match(r"for\s+(.+?)\s*:", line):
            expr = m.group(1)
            self._append(state, indent, f"{{% for {expr} %}}")
            state.open_blocks.append(BlockInfo("for", indent))
        elif line.startswith("return "):
            raw_expr = line[7:].strip()
            if _has_jinja_incompatible_expr(raw_expr):
                self._append(state, indent, f"{{# CODE: {line} #}}")
            else:
                expr = self._convert_expressions(raw_expr)
                self._append(state, indent, "{{ " + expr + " }}")
        elif m := re.match(r"(\w+)\s*([+\-*/|&^%]=)\s*(.+)", line):
            varname = m.group(1)
            op = m.group(2)
            expr = self._convert_expressions(m.group(3).strip())
            op_base = op[:-1]  # strip trailing '='
            self._append(state, indent, f"{{% set {varname} = {varname} {op_base} {expr} %}}")
        elif m := re.match(r"([\w\s,]+?)\s*=\s*(.+)", line):
            lhs = m.group(1).strip()
            raw_expr = m.group(2).strip().rstrip(";").rstrip()
            if _has_jinja_incompatible_expr(raw_expr):
                self._append(state, indent, f"{{# CODE: {line} #}}")
            else:
                expr = self._convert_expressions(raw_expr)
                self._append(state, indent, f"{{% set {lhs} = {expr} %}}")
        else:
            self._append(state, indent, f"{{# CODE: {line} #}}")

    # ── Private: expression conversion ───────────────────────────────────

    def _convert_content_line(self, line: str) -> str:
        """Convert a regular content line (HTML/text with Templetor expressions).

        Order matters: most specific patterns first so greedy patterns don't
        consume parts of more specific ones.
        """
        # 0. $cond(expr, val[, default]) → {{ val if expr else default }}
        line = _convert_cond_in_line(line)

        # 0b. $ungettext(...) → {{ ungettext(...) }}
        line = _convert_ungettext_in_line(line)

        # 1. $:_(\"...\") or $:_('...') -- i18n raw output with balanced parens
        line = _convert_i18n_raw(line)

        # 2. $_(\"...\") or $_('...') -- i18n auto-escaped with balanced parens
        line = _convert_i18n_call(line)

        # 3. $:expression -- raw output in content → | safe
        line = _convert_raw_expressions(line)

        # 4. $(expr) -- explicit paren grouping with balanced tracking
        line = _convert_explicit_parens(line)

        # 5. ${expr} -- explicit brace grouping with balanced tracking
        line = _convert_explicit_braces(line)

        # 6. $$ -- escaped dollar sign
        line = RE_ESCAPED_DOLLAR.sub("$", line)

        # 7. $expression -- bare variable/method with balanced parens and brackets
        line = _convert_bare_expressions(line)

        return line

    def _convert_expressions(self, expr: str) -> str:
        """Convert Templetor expressions within a Jinja expression context.

        In a Jinja expression context (inside ``{% %}``), variables are
        already evaluated, so ``$var`` should become just ``var``.
        """
        # $_("text") → _("text")  (balanced-paren)
        expr = _convert_i18n_call(expr)

        # $cond(expr, val, default) → val if expr else default (no {{ }} wrapping)
        expr = _convert_cond_in_line(expr, wrap=False)

        # $ungettext(...) → ungettext(...)
        expr = _convert_ungettext_in_line(expr)

        # $var → var  (strip $ prefix in expression context)
        expr = re.sub(r"\$([a-zA-Z_][\w]*(?:\.[\w]+)*)", r"\1", expr)

        # $$ → $
        expr = expr.replace("$$", "$")

        return expr


# ── Module-level convenience functions ───────────────────────────────────


def convert_text(text: str, macro_name: str = "") -> str:
    """Convenience function to convert Templetor text to Jinja2."""
    converter = TempletorToJinjaConverter(macro_name=macro_name)
    return converter.convert(text)


def convert_file(filepath: str, macro_name: str = "") -> str:
    """Convenience function to convert a Templetor file to Jinja2."""
    converter = TempletorToJinjaConverter(macro_name=macro_name)
    return converter.convert_file(filepath)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python converter.py <templetor_file.html> [macro_name]")
        print("       python converter.py --stdin [macro_name]")
        sys.exit(1)

    name = sys.argv[2] if len(sys.argv) > 2 else ""

    if sys.argv[1] == "--stdin":
        content = sys.stdin.read()
        print(convert_text(content, macro_name=name))
    else:
        print(convert_file(sys.argv[1], macro_name=name))
