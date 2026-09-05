---
applyTo: "static/css/**,openlibrary/components/**,openlibrary/templates/**,openlibrary/macros/**,openlibrary/plugins/openlibrary/js/**"
---
# UI review checklist

Derived from [`docs/ai/design.md`](../../docs/ai/design.md) and [`docs/ai/web-components.md`](../../docs/ai/web-components.md), which hold the rules and their rationale. Flag any added or modified line that:

- Uses a raw color (hex, `rgb()`, `hsl()`, named) instead of a semantic `--color-*` token.
- Uses a deprecated alias such as `--grey`, `--white`, `--light-grey`, `--lightest-grey`, `--beige`, or `--primary-blue`. Point to the semantic token.
- Puts a `transition` on `background`, `color`, or `border-color` for a `:hover` state — hover changes must be instant.
- Changes `font-weight` on `:hover` or a selected state (layout shift).
- Adds a `:hover` rule outside `@media (hover: hover) and (pointer: fine)`.
- Sets `font-size` below 16px on a text-entry control (iOS Safari zooms on focus).
- Adds a new `ol-*` Lit component without JSDoc (`@prop`/`@fires`/`@slot`), a demo partial under `openlibrary/templates/design/components/`, and a `COMPONENTS` row in `openlibrary/plugins/openlibrary/design.py`.
- Copies the surrounding file's legacy pattern where it conflicts with the above. Only the touched declaration needs to comply; don't ask for whole-file migrations.
