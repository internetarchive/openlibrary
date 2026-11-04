# Internationalization (i18n)

How Open Library translates its UI across locales: the translation **pipeline**
(string extraction, the `openlibrary-i18n` repo, Weblate, the AI-assisted flow)
and the **rendering** mechanics that put a translated string on the page
(Templetor vs Jinja, the `data-i18n` JS bridge, `{% trans %}`, POT
regeneration).

**What belongs here:** how strings are extracted, translated, and rendered.
Migration *progress* lives in epic **#13061**, not here.

## In this section

- [`i18n-pipeline.md`](i18n-pipeline.md) — the end-to-end translation pipeline.
  The migration to `openlibrary-i18n` is complete; this is the stable reference
  for which repo a `.po` file lives in and how a translation reaches production.
- [`i18n-rendering.md`](i18n-rendering.md) — the rendering/templating mechanics.

Owned by the i18n division.
