# Internationalization (i18n)

How Open Library translates its UI across locales: the translation **pipeline**
(string extraction, the `openlibrary-i18n` repo, Weblate, the AI-assisted flow)
and how to **write** translatable strings for the server and the browser
(Jinja, Templetor, `_()` in browser JS, POT regeneration), and the
**rendering** internals that put a translated string on the page.

**What belongs here:** how strings are written, extracted, translated, and rendered.
Migration *progress* lives in epic **#13061**, not here.

## In this section

- [`i18n-pipeline.md`](i18n-pipeline.md) — the end-to-end translation pipeline.
  The migration to `openlibrary-i18n` is complete; this is the stable reference
  for which repo a `.po` file lives in and how a translation reaches production.
- [`i18n.md`](i18n.md) — the how-to for server and browser strings: Jinja,
  Templetor, `_()` / `ngettext()` in browser JS, Vue and Lit, extraction rules.
- [`i18n-rendering.md`](i18n-rendering.md) — server-side internals: the Jinja
  environment, compiled `.mo` and browser catalog files, fragile spots.

Owned by the i18n division.
