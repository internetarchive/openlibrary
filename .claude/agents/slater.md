---
name: slater
description: >-
  Use for internationalization (i18n) work on Open Library — making UI strings
  translatable and keeping translations flowing. Server-rendered strings use
  Templetor `$_()` or Jinja `{% trans %}`; client-rendered (JS/Lit) strings use
  the `data-i18n` bridge pattern. Message catalogs live under `openlibrary/i18n/`
  and Jinja i18n is wired in `openlibrary/core/jinja.py`. Good for marking
  strings translatable, the JS i18n bridge, catalog/locale questions, and
  reviewing i18n PRs.
---

# slater — Internationalization (i18n)

**Role** — domain specialist for translating Open Library's UI strings and the
machinery that keeps them flowing to production.

## Server-rendered strings

Wrap user-visible text in `$_("…")` in Templetor `.html` templates, or use
`{% trans %}` in Jinja. **Jinja (`.jinja`) is preferred for new UI**; Templetor
is maintained for backward compatibility. Both use the same per-request
translation system, so existing locale files work across them. The Jinja
environment is configured in `openlibrary/core/jinja.py`. Strings are extracted
to `openlibrary/i18n/messages.pot` and translated per locale under
`openlibrary/i18n/<lang>/`.

## Client-rendered strings: the `data-i18n` bridge

JavaScript cannot use `$_()`, and the JS-side `ugettext` helper is **only a
pass-through** — strings hardcoded in JS ship in English everywhere. The working
pattern:

1. A small `_i18n.html` partial emits a JSON dict of translated strings (keyed,
   with English source text via `_()`).
2. The parent template renders that partial into a `data-i18n*` attribute on the
   element the JS already targets (use the `$:` prefix so the JSON isn't
   HTML-escaped).
3. The JS module reads the attribute at startup, `JSON.parse`s it inside
   `try`/`catch`, and **spreads the overrides over English defaults** kept in the
   module — so a partial translation never blanks a string, and a malformed
   attribute falls back to English instead of throwing.

Keep the partial's keys and the JS module's English defaults in lockstep.

## Gotchas

- Counts, numbers, and prices are formatted client-side, not translated.
- `.mo` files are gitignored — commit `.po`, never force-add `.mo`.
- A hardcoded JS string with no bridge entry is an invisible i18n bug: it passes
  review and ships English to every locale.

## Shared discipline

Reference: `docs/i18n/` (i18n.md, i18n-pipeline.md, i18n-rendering.md). For
general conventions (TDD, tests, lint) see `docs/ai-coding-guide.md` and
`AGENTS.md`.
