# Templetor-to-Jinja2 Converter

A Python tool that automatically converts [web.py Templetor](https://webpy.org/docs/0.3/templetor) templates and macros into equivalent [Jinja2](https://jinja.palletsprojects.com/) templates, designed for the Open Library codebase.

## Usage

```bash
# Convert a file (macro name auto-detected from filename)
python converter.py path/to/template.html

# Convert a file with explicit macro name
python converter.py path/to/template.html MyMacro

# Convert from stdin
echo '$def with (name)' | python converter.py --stdin MyMacro
```

```python
from converter import convert_text, convert_file

# Convert from string
jinja = convert_text('$def with (name)\n<p>Hello $name</p>', macro_name='Greeting')

# Convert from file
jinja = convert_file('openlibrary/macros/Hello.html')
```

## Supported Templetor Syntax

| Templetor | Jinja2 | Notes |
|---|---|---|
| `$def with (args)` | `{% macro Name(args) %}...{% endmacro %}` | Macro name from filename or parameter |
| `$def func(args):` | `{% macro func(args) %}...{% endmacro %}` | Inline function definitions |
| `$for ...:` | `{% for ... %}...{% endfor %}` | |
| `$if ...:` / `$elif` / `$else` | `{% if %}...{% elif %}...{% else %}...{% endif %}` | |
| `$ var = expr` | `{% set var = expr %}` | Space after `$` required |
| `$code:` | Jinja set/macro statements | Python assignments → `{% set %}`, defs → `{% macro %}` |
| `$expr` | `{{ expr }}` | Auto-escaped output |
| `$:expr` | `{{ expr \| safe }}` | Raw output — emits `| safe` filter |
| `$(expr)` / `${expr}` | `{{ expr }}` | Explicit grouping |
| `$_("text")` | `{{ _("text") }}` | i18n function calls |
| `$:_("text")` | `{{ _("text") \| safe }}` | i18n raw output — emits `| safe` |
| `$var.attr.method()` | `{{ var.attr.method() }}` | Dotted attribute access |
| `$cond(expr, val, default)` | `{{ val if expr else default }}` | Conditional shorthand (2 or 3 args) |
| `$ungettext(...)` | `{{ ungettext(...) }}` | Plural i18n passthrough |
| `$# comment` | `{# comment #}` | |
| `$$` | `$` | Escaped dollar sign |

## Templates Converted and Tested

The converter was incrementally built and tested against 5 real Open Library templates of increasing complexity:

1. **`openlibrary/macros/Hello.html`** — `$def with` defaults, `$for` loop, `$_.attr` access, `$_()` i18n
2. **`openlibrary/macros/OlPagination.html`** — `$if` conditionals, i18n in HTML attributes, `$var` in attributes
3. **`openlibrary/templates/form.html`** — Nested `$for`/`$if`/`$else`, `$:` raw output, `$ var = expr`, sequential `$if` blocks
4. **`openlibrary/macros/CoverImage.html`** — `$code:` blocks with function defs, `$def` inside `$code:`, nested conditionals, macro calls
5. **`openlibrary/macros/QueryCarousel.html`** — Complex multi-line `$def with` (14 parameters), `$#` comment blocks, nested `$if` inside `$if`, `$:` macro calls with many keyword args

## Assumptions

- **4-space indentation** — Standard Python indentation is assumed for block body detection.
- **`$def with` is the first line** — When present, it defines the template's macro signature.
- **Macro name derivation** — When using `convert_file()`, the macro name is derived from the filename (e.g., `Hello.html` → `Hello`). Override with the `macro_name` parameter.
- **Indentation is preserved** — The converter preserves the original indentation style (spaces, not tabs).
- **Blank lines are preserved** — Blank lines between sibling blocks are maintained in the output.

## Known Limitations

1. **`$while` not supported** — Templetor supports `$while expr:` loops. These are not handled by the converter and will be treated as content lines.

2. **Line continuation (`\`)** — Backslash line continuation in Templetor is not supported.

3. **Nested parentheses in i18n strings** — The regex for `$_("text")` uses `[^)]*` for extra arguments. If the i18n string itself contains a literal `)` (e.g., `$_("foo)")`), the regex may match incorrectly. This is a rare edge case.

4. **`$code:` blocks with complex Python** — Multi-line Python logic in `$code:` blocks (list comprehensions, decorators, multi-line function calls) may not convert perfectly. Complex blocks should be reviewed manually.

5. **Templetor `loop` object** — Templetor provides `loop.index`, `loop.first`, `loop.last`, `loop.parity` inside `$for` blocks. Jinja has equivalent `loop.index`, `loop.first`, `loop.last` natively, but `loop.parity` (returns "odd"/"even") has no direct Jinja equivalent and would need `loop.cycle('odd', 'even')`.

6. **Nested `$def func()` inside templates** — These are converted to `{% macro %}` blocks. The function body indentation is detected using `max(line_indent, indent + 4)`, which assumes 4-space indent.

7. **`$try`/`$except`/`$finally`** — The converter handles these syntactically, but Jinja2 does not natively support try/except blocks. These would require custom extensions.

## Running Tests

```bash
cd scripts/templetor_converter
uv run --with pytest pytest test_converter.py -v
```

84 tests covering all supported syntax patterns, the 5 reference templates, edge cases, and indentation sensitivity.
