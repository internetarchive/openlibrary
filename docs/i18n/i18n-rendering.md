# i18n Rendering — server-side internals

> **Status:** reference.
> **How to write translatable strings:** [i18n.md](i18n.md) (Jinja, Templetor, browser JS, Vue, extraction rules).
> **Where translations come from:** [i18n-pipeline](i18n-pipeline.md). Read it before editing a `.po` file.
> **Accessibility:** a separate domain, see [a11y](../frontend/a11y.md).
> **Last reviewed:** 2026-11-28

This page explains how the server gets translations into Jinja and Templetor at render time, what `make i18n` produces, and what breaks silently.

---

## How it works

### Translation sources

| Context | Mechanism |
|---------|-----------|
| Templetor `.html` templates | `$_("string")`, `$ungettext(s1, s2, n, key=val)` |
| Jinja `.jinja` templates | `{{ _('string') }}`, `{{ ngettext(s1, s2, n) }}`, `{% trans %}...{% endtrans %}` |
| Browser JavaScript, Lit, Vue | `_()` / `ngettext()` from `i18n.js` (see [i18n.md](i18n.md)) |

All of these read the `.po` files under `openlibrary/i18n/<lang>/`. Those files are populated at image-build time from the `openlibrary-i18n` repo (see [i18n-pipeline](i18n-pipeline.md)).

### Compiled outputs

The language directories under `openlibrary/i18n/` hold `messages.po`. `make i18n` (which runs `python ./scripts/i18n-messages compile`) produces two outputs per language:

| Output | Reader |
|--------|--------|
| `openlibrary/i18n/<lang>/messages.mo` | The server. Templetor and Jinja read it per request. |
| `static/build/i18n/<lang>.js` | The browser. The page head loads it as `window.OL_I18N`. |

The browser file's strings come from the `_()` / `ngettext()` calls in the JS sources, not from `messages.pot`. Plural forms use the same `Plural-Forms` rule as the server, exposed as `window.OL_I18N_PLURAL`. See [i18n.md](i18n.md) for the details.

### Jinja environment

Configured in `openlibrary/core/jinja.py` via `get_jinja_env()`:

- `jinja2.ext.i18n` is enabled.
- `install_gettext_callables(gettext, ngettext, newstyle=True)` wires the per-request `.mo` translations (`load_translations(lang).ugettext`) into Jinja.
- `ext.i18n.trimmed = True` strips leading and trailing whitespace from `{% trans %}` blocks at render time.
- `install_gettext_callables` registers `_`, `gettext` and `ngettext` as globals. In Jinja `_` is the registered gettext callable, not a special construct as `$_()` is in Templetor.

Templetor's `$_()` and `$ungettext()` read the same per-request `.mo` translations. Extraction uses `openlibrary.i18n:extract_templetor` for Templetor and `jinja2.ext:babel_extract` for Jinja.

---

## Key files

| File | Purpose |
|------|---------|
| `openlibrary/core/jinja.py` | Jinja environment setup; `install_gettext_callables` |
| `openlibrary/i18n/` | `messages.pot` plus per-language `<lang>/` directories |
| `openlibrary/i18n/__init__.py` | Compile step, `_javascript_msgids()`, `plural_rule()` |
| `openlibrary/core/shell/head.py` | `_javascript_catalog_url()` for the browser catalog |
| `openlibrary/macros/AffiliateLinks.html.jinja` | Reference Jinja template using the i18n patterns |
| `openlibrary/tests/core/test_jinja.py` | `test_translations_via_gettext_callables` |

---

## Testing

```bash
# Jinja translation forms
docker compose run --rm home python -m pytest openlibrary/tests/core/test_jinja.py -xvs

# JS gettext helpers (_, ngettext, lookup)
npm test tests/unit/js/i18n.test.js

# Validate the translation files
make test-i18n
```

To regenerate `messages.pot` and check an entry, see [i18n.md](i18n.md).

---

## Fragile spots

- **jsdef `_()` / `ungettext()` are pass-throughs.** Strings in jsdef templates show English in every language.
- **A string that extraction misses shows English.** Extraction only sees literal `_()` / `ngettext()` calls; see the extraction rules in [i18n.md](i18n.md).
- **Whitespace in `{% trans %}` blocks.** Babel's extraction doesn't apply `ext.i18n.trimmed`. A block written without `-%}` / `{%-` produces a `.pot` entry that never matches the runtime lookup, so translations exist but never apply.
- **Untranslated strings show English**, in the browser as on the server.
- **Newstyle gettext takes named placeholders only.** A positional `%s` doesn't work in Jinja; use `%(name)s`.
- **Missing browser catalog.** Before `make i18n` has written `static/build/i18n/<lang>.js`, the page head emits no catalog URL and the browser shows English.

---

## Dependencies

**Depends on:**
- `openlibrary/core/jinja.py`, wired into the web.py request lifecycle.
- [frontend](../frontend/README.md): Lit components call `_()` from `i18n.js`.

**Depended on by:**
- All user-facing pages (via `$_()` and `{{ _() }}`).
- All Lit components with user-visible text.
