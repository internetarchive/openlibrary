# i18n Rendering — templates & JavaScript

> **Status:** reference — the rendering mechanics below are stable.
> **Companion:** this is *how* a string gets translated at render time. *Where* translations
> live and how they flow to production (the authoritative `openlibrary-i18n` store, the AI
> pipeline, the `olbase` bake, the rules about fuzzy entries) is [[i18n-pipeline]] — read that
> before editing a `.po`.
> **Note:** a11y (accessibility) is a separate domain — see [[a11y]].
> **Sources:** `raw/openlibrary-docs-ai/i18n.md` · **Last reviewed:** 2026-10-06

Internationalization (i18n) covers translation of UI strings across two template engines (Templetor and Jinja) and a bridge pattern for JavaScript/Lit components. This page is the render-time half; the pipeline that *produces* the translations these mechanics consume is [[i18n-pipeline]].

---

## How It Works

### Two translation systems

| Context | Mechanism |
|---------|-----------|
| Templetor `.html` templates | `$_("string")` |
| Jinja `.jinja` templates | `{{ _('string') }}`, `{% trans %}...{% endtrans %}` |
| JavaScript / Lit components | `data-i18n` bridge (server renders JSON → JS reads it) |

All paths use the same `.po`/`.mo` locale files under `openlibrary/i18n/<lang>/`. Those files are
populated at image-build time from the authoritative `openlibrary-i18n` store and compiled to `.mo`
by the `olbase` bake — see [[i18n-pipeline]]. At render time the engines only ever read the compiled
`.mo`; this page is about that read side.

### Jinja environment

Configured in `openlibrary/core/jinja.py` via `get_jinja_env()`:
- `jinja2.ext.i18n` extension enabled
- `install_gettext_callables(gettext, ngettext, newstyle=True)` wires per-request `.mo` translations into Jinja
- `ext.i18n.trimmed = True` strips leading/trailing whitespace from `{% trans %}` blocks at render time
- Auto-registers `_`, `gettext`, `ngettext` as globals — no manual wiring needed

**New templates should use Jinja (`.jinja`).** Templetor is maintained for backward compatibility only.

### The `data-i18n` bridge (for JavaScript/Lit)

JavaScript cannot call `$_()`. The `ugettext` JS helper in the codebase is a **pass-through only** — strings hardcoded in JS ship in English everywhere.

**The pattern** (4 steps):

**1. Write a `_i18n.html` partial** that returns a JSON dict of translated strings:

```html
$def with ()
$ search_modal_i18n = {
$     "inputPlaceholder":  _("Search books, authors…"),
$     "closeAria":         _("Close search"),
$     "noResults":         _("No results found"),
$ }
$json_encode(search_modal_i18n)
```

Leading comment must name: which JS file consumes this partial, and which JS constant holds the English defaults.

**2. Drop the JSON into a `data-*` attribute** on the element your JS already targets:

```html
<button
  class="search-bar-trigger"
  data-i18n-ui="$:render_template('search/search_modal_i18n')"
></button>
```

Use `$:` (not `$`) — without the colon, Templetor HTML-escapes the JSON. For two independent payloads on one element, use two attribute names (`data-i18n` and `data-i18n-ui`).

**3. Keep English defaults in the JS module** — they are the fallback AND the extraction source:

```js
export const DEFAULT_SEARCH_MODAL_STRINGS = {
    inputPlaceholder: 'Search books, authors…',
    closeAria: 'Close search',
    noResults: 'No results found',
};

export function searchModalStringsFromElement(el) {
    let overrides = null;
    try {
        const raw = el?.dataset?.i18nUi;
        if (raw) overrides = JSON.parse(raw);
    } catch { /* fall through to defaults */ }
    return overrides
        ? { ...DEFAULT_SEARCH_MODAL_STRINGS, ...overrides }
        : DEFAULT_SEARCH_MODAL_STRINGS;
}
```

Spreading overrides over defaults means partial translations never blank out a string. Wrap `JSON.parse` in `try/catch` — a bad attribute on one element must not take down the page.

**4. Use the merged strings to build DOM:**

```js
const strings = searchModalStringsFromElement(trigger);
input.placeholder = strings.inputPlaceholder;
```

---

## How It Is Used

### Adding a translatable string (Jinja)

```jinja
{# Short string #}
{{ _('Recently added') }}

{# String with placeholder — named only, no positional %s #}
{{ _('Look for %(title)s at %(store)s', title=book.title, store=store.name) }}

{# Plural #}
{{ ngettext('%(count)d book', '%(count)d books', books|length) }}

{# Inline link — embed HTML directly, use |safe #}
{{ _('Learn more <a href="/help">here</a>.') | safe }}
```

### Regenerating the POT file

```bash
docker compose run --rm home python ./scripts/i18n-messages extract
```

Then verify `openlibrary/i18n/messages.pot` has no leading `\n` in new entries.

### `{% trans %}` block — when to use

Only for: multi-line strings with HTML via `|safe` variables, or strings needing pluralization with `ngettext`. For short strings with a single inline `<a>` tag, use `{{ _('...') | safe }}` — it's simpler and matches the 97+ existing translated strings with `<a>` tags.

```jinja
{# GOOD — short string with inline link #}
{{ _('Learn more <a href="/help">here</a>.') | safe }}

{# ONLY use {% trans %} for complex multi-line strings #}
{% trans -%}
This is a long paragraph that really needs the block form
for readability, with multiple HTML elements.
{%- endtrans %}
```

**Critical**: use `-%}` on opening and `{%-` on closing. `ext.i18n.trimmed` strips whitespace at render time but **Babel's extraction does not** — the extracted `.pot` entry must match what Jinja looks up at runtime or translations will never be found.

---

## Jinja vs Templetor Comparison

| Aspect | Templetor (`.html`) | Jinja (`.jinja`) |
|--------|---------------------|------------------|
| Translation syntax | `$_("string")` | `{{ _('string') }}`, `{% trans %}` |
| Placeholders | Python `%` inside `$_()` | Named only: `%(name)s` |
| Plural | `$ungettext(s1, s2, n)` | `{{ ngettext(s1, s2, n) }}` |
| HTML in strings | `$_("...<a>...</a>") \| safe` | `{{ _('...') \| safe }}` |
| Extraction | `openlibrary.i18n:extract_templetor` | `jinja2.ext:babel_extract` |
| Status | Legacy | **Preferred for new work** |

---

## Key Files

| File | Purpose |
|------|---------|
| `openlibrary/core/jinja.py` | Jinja environment setup; `install_gettext_callables` |
| `openlibrary/i18n/` | `messages.pot` + per-locale `<lang>/` directories |
| `openlibrary/templates/search/availability_i18n.html` | Reference `_i18n.html` partial |
| `openlibrary/templates/search/search_modal_i18n.html` | Reference `_i18n.html` partial |
| `openlibrary/plugins/openlibrary/js/search-modal/constants.js` | Reference JS reader + English defaults |
| `openlibrary/templates/lib/nav_head.html` | How partials are wired onto trigger buttons |
| `openlibrary/macros/AffiliateLinks.html.jinja` | Reference Jinja template using all i18n patterns |
| `openlibrary/tests/core/test_jinja.py` | `test_translations_via_gettext_callables` — all four paths |
| `tests/unit/js/searchModalConstants.test.js` | Tests for the reader/merge logic |

---

## Configuration

No runtime env vars. Translation files under `openlibrary/i18n/<lang>/` are compiled `.mo` files loaded per request.

**Strings flow (current, post-migration):** OL source → `messages.pot` → the `openlibrary-i18n`
store, where translations are AI-generated on each `.pot` change (humans correct via Weblate) →
`olbase` pulls `openlibrary-i18n` at image build and compiles to `.mo` → served per-request. The
authoritative source is `openlibrary-i18n`, not the `.po` files committed in `openlibrary`. See
[[i18n-pipeline]] for the full flow. *(This replaced the older POEditor-based management flow.)*

---

## Testing

```bash
# Jinja translation paths
docker compose run --rm home python -m pytest openlibrary/tests/core/test_jinja.py -xvs

# JS bridge logic
npm test tests/unit/js/searchModalConstants.test.js

# Regenerate POT and verify no mangled entries
docker compose run --rm home python ./scripts/i18n-messages extract
grep -A3 'msgid "Recently added"' openlibrary/i18n/messages.pot
```

---

## What's Broken / Fragile

- **`ugettext` JS helper is a pass-through** — any JS string not using the `data-i18n` bridge ships in English regardless of the user's language setting. This is a known architectural gap; the bridge pattern is the correct fix.
- **Whitespace sensitivity in `{% trans %}` blocks** — forgetting `-%}` / `{%-` produces `.pot` entries with leading whitespace that never match the runtime lookup. Silent failure: translations exist but never apply.
- **Partial translations** show English fallback for missing keys (by design, via the spread pattern). But if the partial itself is missing or the attribute name is wrong, the entire component falls back to English silently.

---

## Common Confusion

- **`$:render_template` vs `$render_template`** — the colon is required. Without it, Templetor HTML-escapes the JSON output, breaking `JSON.parse` in JS.
- **Newstyle gettext only supports named placeholders** — `%s` (positional) won't work in Jinja. Use `%(name)s` always.
- **`{{ _() }}` is not a special Jinja override** — unlike Templetor where `$_()` is a special construct, in Jinja `_` is just the registered gettext callable. All four forms (`_()`, `gettext()`, `ngettext()`, `{% trans %}`) call the same function.
- **Jinja `{% trans %}` whitespace** — `ext.i18n.trimmed = True` handles render-time whitespace but Babel extraction doesn't trim. The mismatch causes silent translation misses.

---

## Dependencies

**Depends on:**
- [[core-operations]] — Jinja environment wired into the web.py/Infogami request lifecycle; `openlibrary/core/jinja.py` is the setup point
- [[frontend]] — Lit components use the `data-i18n` bridge
- [[a11y]] — accessibility patterns are a separate domain

**Depended on by:**
- All user-facing pages (via `$_()` and `{{ _() }}`)
- All Lit components with user-visible text

---

*Sources: `raw/openlibrary-docs-ai/i18n.md` · a11y is a separate domain → [[a11y]] · See [[README]] · [[METHODOLOGY]]*
