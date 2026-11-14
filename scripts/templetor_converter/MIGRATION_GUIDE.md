# Templetor → Jinja2 Migration Guide

> **Converter location:** `scripts/templetor_converter/converter.py`
> **Test suite:** `scripts/templetor_converter/test_converter.py` (126 tests)
> **Last updated:** 2026-06-11

## Overview

This guide covers the automated conversion of Open Library's 371 Templetor (web.py) templates
to Jinja2, the manual work remaining, and the step-by-step migration process.

### Current Conversion Stats

| Metric | Value |
|--------|-------|
| Total templates | 371 |
| Jinja2 compiles OK | 349 (94%) |
| Macros (100%) | 79/79 |
| Templates (~93%) | 270/291 |
| `{# CODE: #}` comments (manual review) | 253 |
| Raw `$` lines outside CODE | 0 |

## What the Converter Handles Automatically

The converter handles **~94%** of all templates with zero manual intervention:

### Fully Supported Patterns

| Templetor | Jinja2 | Notes |
|-----------|--------|-------|
| `$def with (args)` | `{% macro Name(args) %}` | Macro name from filename; hyphens → underscores |
| `$def func(args):` | `{% macro func(args) %}` | Local function defs in `$code:` blocks |
| `$for ...:` | `{% for ... %}` | With expression conversion |
| `$if ...:` / `$elif` / `$else` | `{% if %}` / `{% elif %}` / `{% else %}` | |
| `$ var = expr` | `{% set var = expr %}` | Including tuple unpacking `$ a, b = expr` |
| `$ var += expr` | `{% set var = var + expr %}` | Augmented assignment |
| `$code:` blocks | `{% set %}` / `{% macro %}` | Multi-line merging, Python comment stripping |
| `$expr` | `{{ expr }}` | Bare variable output |
| `$ expr` | `{{ expr }}` | Dollar-space also works |
| `$:expr` | `{{ expr \| safe }}` | Raw (unescaped) output |
| `$(expr)` | `{{ expr }}` | Explicit paren grouping with balanced tracking |
| `${expr}` | `{{ expr }}` | Explicit brace grouping |
| `$:func(args)` | `{{ func(args) \| safe }}` | Method calls with balanced parens |
| `$:'string'.method()` | `{{ 'string'.method() \| safe }}` | String literal scanning |
| `$:_.get(k, v)` | `{{ _.get(k, v) \| safe }}` | Method access on `_` object |
| `$:_(\"text\")` | `{{ _(\"text\") \| safe }}` | i18n raw output |
| `$_(\"text\")` | `{{ _(\"text\") }}` | i18n auto-escaped |
| `$cond(expr, val, default)` | `{{ val if expr else default }}` | Jinja2 ternary |
| `$ungettext(...)` | `{{ ungettext(...) }}` | Passthrough |
| `$$` | `$` | Escaped dollar |
| `$# comment` | `{# comment #}` | Comments |
| `\"%.2f\" % val` | `\"%.2f\" % val` | % string formatting (valid Jinja2) |
| `{\"key\": val}` | `{\"key\": val}` | Dict literals (valid Jinja2) |
| Trailing semicolons | Stripped | `$ x = 'hello';` → `{% set x = 'hello' %}` |
| Type hints | Stripped | `$def with (x: bool)` → `{% macro M(x) %}` |
| Hyphenated names | Sanitized | `forgot-ia.html` → `{% macro forgot_ia() %}` |
| `*args` / `**kwargs` | Stripped | Jinja2 macros don't support variadic args |

### Patterns That Produce `{# CODE: ... #}` Comments

These patterns can't be auto-converted and are wrapped as Jinja2 comments for manual review:

| Pattern | Example | Count | How to Fix |
|---------|---------|-------|------------|
| **List/generator comprehensions** | `[x for x in items if cond]` | ~30 | Rewrite as `{% for %}` loop or move to view layer |
| **Subscript assignment** | `context['key'] = value` | ~16 | Move to view layer or use `{% do %}` extension |
| **Dict comprehension** | `{k: v for k, v in items}` | ~5 | Move to view layer |
| **Lambda** | `sorted(items, key=lambda x: x[1])` | ~3 | Move to view layer |
| **Trailing-dot numbers** | `100.` | ~2 | Change to `100` or `100.0` |
| **`hasattr()` checks** | `hasattr(doc, 'availability')` | ~3 | Use `doc.availability is defined` or move to view |
| **`dict()` constructor** | `dict((k, v) for ...)` | ~2 | Move to view layer |
| **`next()` with generator** | `next((e for e in ...), default)` | ~1 | Move to view layer |
| **Side-effect calls** | `render_items.append(x)` | ~2 | Move to view layer |
| **`isinstance()` checks** | `isinstance(a, str)` | ~1 | Move to view layer |
| **Complex expressions** | Various Python-only constructs | ~10 | Case-by-case manual conversion |

### Top Templates by CODE Comment Count

| Template | CODE Comments | % of Lines |
|----------|:---:|:---:|
| `search/sort_options.html` | 51 | 59% |
| `type/edition/view.html` | 41 | 6% |
| `type/work/view.html` | 41 | 6% |
| `admin/imports.html` | 14 | 10% |
| `macros/SearchResultsWork.html` | 13 | 4% |
| `macros/databarWork.html` | 13 | 15% |
| `macros/RawQueryCarousel.html` | 12 | 18% |

## Remaining Jinja2 Compilation Failures (22 templates)

These templates fail Jinja2 parsing after conversion and need manual fixes:

| Category | Count | Description |
|----------|:---:|-------------|
| Other syntax | 9 | Various edge cases (unexpected tokens, malformed expressions) |
| Unexpected chars | 4 | `\`, `#`, `?` in content conflicting with Jinja2 parser |
| Brace syntax | 4 | Nested `{}` in expressions confused with Jinja2 delimiters |
| Block nesting | 3 | `else`/`elif` tags outside matching `if` blocks |
| Trailing dot | 2 | `{{ name. }}` — variable followed by literal dot |

## Migration Steps

### Phase 1: Run the Converter (Day 1)

```bash
# Convert a single template
cd scripts/templetor_converter
python converter.py ../../openlibrary/macros/Hello.html

# Convert with a specific macro name
python converter.py ../../openlibrary/macros/Hello.html Hello

# Convert from stdin
echo '$def with (name)' | python converter.py --stdin Template

# Batch convert all macros (write to output directory)
python3 -c "
import os
from converter import convert_file

macros_dir = '../../openlibrary/macros'
out_dir = '../../openlibrary/macros_jinja'
os.makedirs(out_dir, exist_ok=True)

for f in sorted(os.listdir(macros_dir)):
    if f.endswith('.html'):
        name = f.replace('.html', '')
        result = convert_file(os.path.join(macros_dir, f), macro_name=name)
        with open(os.path.join(out_dir, f), 'w') as out:
            out.write(result)
        print(f'Converted: {f}')
"
```

### Phase 2: Validate Jinja2 Compilation (Day 1)

```bash
# Verify all converted templates compile with Jinja2
cd scripts/templetor_converter
uv run --with jinja2 python3 -c "
import os, jinja2
from converter import convert_file

env = jinja2.Environment()
macros_dir = '../../openlibrary/macros'
files = sorted(f for f in os.listdir(macros_dir) if f.endswith('.html'))

for f in files:
    name = f.replace('.html', '')
    path = os.path.join(macros_dir, f)
    result = convert_file(path, macro_name=name)
    try:
        env.parse(result)
    except jinja2.TemplateSyntaxError as e:
        print(f'FAIL: {name} L{e.lineno}: {e.message}')
"
```

### Phase 3: Review `{# CODE: #}` Comments (Week 1)

Each `{# CODE: ... #}` comment marks a line that needs manual conversion. Search for them:

```bash
# Find all CODE comments in converted output
grep -rn '{# CODE:' openlibrary/macros_jinja/ | head -50

# Count by template
grep -rl '{# CODE:' openlibrary/macros_jinja/ | wc -l
```

**Conversion strategies for CODE comments:**

1. **List comprehensions** → **Recommended: move to Python view layer.**
   Pass the filtered/transformed list as a template variable. If that's not feasible,
   rewrite as a `{% for %}` loop:
   ```
   {# CODE: previews = [e for e in editions if e.get('ocaid')] #}
   ```
   becomes (in the Python view):
   ```python
   # In your view/handler
   previews = [e for e in editions if e.get('ocaid')]
   # Then pass `previews` as a template variable
   ```
   Or as a Jinja2 workaround (relies on Python list mutation):
   ```jinja2
   {% set previews = [] %}
   {% for e in editions %}
     {% if e.get('ocaid') %}
       {% set _ = previews.append(e) %}
     {% endif %}
   {% endfor %}
   ```

2. **Subscript assignment** → Move to view layer:
   ```
   {# CODE: context['reloadId'] = reload_id #}
   ```
   This can't be expressed in Jinja2. Pass `reloadId` as a template variable instead.

3. **Dict/set comprehensions** → Move to view layer. These have no Jinja2 equivalent.

4. **Lambda expressions** → Move to view layer. Pass the sorted/filtered result as a variable.

5. **Trailing-dot numbers** → Simple text fix:
   ```
   {{ "%.2f" % (val * 100.) }}  →  {{ "%.2f" % (val * 100) }}
   ```

### Phase 4: Fix Compilation Failures (Week 1-2)

For the ~22 templates that fail Jinja2 compilation, common fixes:

1. **Unexpected characters** — Escape or remove characters that Jinja2's parser chokes on
2. **Block nesting** — Ensure every `{% if %}`, `{% for %}`, `{% macro %}` has proper closing
3. **Brace syntax** — Use Jinja2's `|default({})` filter instead of bare `{}` in some contexts

### Phase 5: Runtime Testing (Week 2-3)

Even templates that compile may have runtime differences:

1. **`%` string formatting** — Jinja2 delegates to Python's `%` operator, which works for strings
   but may behave differently for edge cases (e.g., `None` formatting)
2. **Variable scoping** — Jinja2 has stricter scoping than Templetor. Variables set inside
   `{% for %}` or `{% if %}` blocks may not be visible outside
3. **`$var` attribute access** — `$page.title` becomes `{{ page.title }}` but Jinja2 uses
   `getattr` then `getitem` which may differ from Python's attribute resolution
4. **`| safe` filter** — The converter adds `| safe` for `$:expr`. Verify this doesn't introduce
   XSS vulnerabilities in new contexts

### Phase 6: Runtime Infrastructure (Week 2-4)

The converter handles template syntax, but the runtime environment also needs setup:

1. **Context processors** — Make `web.ctx`, `web.input()`, `site.*` available as Jinja2
   globals. Implement in `openlibrary/app.py` or a new `openlibrary/jinja_globals.py`.
2. **Custom filters** — Implement `changequery()`, `urlencode()`, `commify()` as Jinja2
   filters. Create `openlibrary/jinja_filters.py` and register in the Jinja2 environment.
3. **Permission checks** — Expose `is_admin()`, `is_librarian()` as template globals.
4. **i18n** — Ensure `_()` and `ungettext()` are available as Jinja2 globals.
5. **Template inclusion** — Map `render_template()` to Jinja2's `{% include %}` or
   `{% import %}`. Update all `render_template()` calls in converted templates.
6. **Macro calls** — Convert `$:macros.Name()` to `{{ Name() }}` or `{% call %}` syntax.
   Jinja2 macros are imported differently than Templetor's `macros.Name()` pattern.

### Phase 7: Incremental Deployment (Week 4+)

1. **Hybrid mode** — Run both Templetor and Jinja2 side-by-side during migration
2. **Route-by-route** — Convert and deploy one page at a time
3. **A/B testing** — Compare Templetor and Jinja2 output for correctness
4. **Performance testing** — Jinja2 should be comparable or faster than Templetor

## Running the Test Suite

```bash
cd scripts/templetor_converter

# Run all tests (requires pytest)
uv run --with pytest pytest test_converter.py -v

# Run with Jinja2 available (includes Jinja2 compilation test)
uv run --with pytest --with jinja2 pytest test_converter.py -v

# Run a specific test class
uv run --with pytest pytest test_converter.py::TestTemplate4_CoverImage -v

# Run just the Jinja2 compilation validation
uv run --with pytest --with jinja2 pytest test_converter.py::TestJinja2Compilation -v
```

## Known Limitations

1. **`$continue`** — Templetor's `$continue` inside `$for` loops has no Jinja2 equivalent.
   The converter outputs `{{ continue }}` which will fail at runtime. Use `{% continue %}`
   if using Jinja2 2.10+.

2. **`$var(` syntax** — Templetor allows `$var(arg)` to call a variable as a function.
   Jinja2 doesn't support this. These are wrapped as CODE comments.

3. **Line continuation backslash (`\`)** — Not handled by the converter.

4. **Nested bracket tracking** — The expression scanner doesn't handle strings containing
   brackets (e.g., `$:foo['key with ] inside']`). Extremely rare edge case.

5. **`_convert_expressions` context** — The i18n functions (`_convert_i18n_raw`,
   `_convert_i18n_call`) may produce `{# CODE: #}` when called from Jinja expression
   context (inside `{% %}` tags). Review any `{% set %}` lines containing `{# CODE: #}`.

6. **`vendor/` templates excluded** — Infogami templates in `vendor/infogami/` are not
   included in the conversion stats and are handled separately.

## Files

| File | Lines | Purpose |
|------|:---:|---------|
| `scripts/templetor_converter/converter.py` | 1,212 | Main converter |
| `scripts/templetor_converter/test_converter.py` | 1,273 | Test suite (126 tests) |
| `scripts/templetor_converter/MIGRATION_GUIDE.md` | — | This file |
