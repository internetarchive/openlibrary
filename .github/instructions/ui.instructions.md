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
- Writes a raw `cubic-bezier()` or a bare `ms` duration instead of the `--ease-*` / `--duration-*` tokens in `static/css/tokens/motion.css`.
- Adds a `transition` or `animation` without a matching `@media (prefers-reduced-motion: reduce)` override.
- Scales a menu row, drawer item, or surface on `:active`, or uses a press-scale literal instead of `--press-scale`, `-compact`, or `-wide`.
- Gives an overlay its own scrim value, or blurs/dims behind a non-modal panel — the scrim is `--overlay-backdrop-color` / `--overlay-backdrop-blur`, modal surfaces only.
- Hard-codes a menu-row height or inset instead of `--menu-row-height` / `--menu-row-inset` / `--menu-row-padding-inline`, or tints a selected row.
- Hard-codes overline styling (small caps heading) instead of the `--*-overline` typography tokens.
- Uses `left`, `right`, `margin-left`, `padding-right`, or `text-align: left` where a logical property (`inset-inline-end`, `margin-inline-start`, `text-align: start`) would mirror under `dir="rtl"`.
- Uses a breakpoint off the scale in `static/css/tokens/breakpoints.css`, or `min-width: N+1` instead of `max-width: N-1`.
- Hand-inlines an `<svg>` for a glyph in `static/icons/src/` instead of the `icon()` macro (server) or `<ol-icon>` (client / shadow DOM).
- Adds a new `ol-*` Lit component without JSDoc (`@prop`/`@fires`/`@slot`), a demo partial under `openlibrary/templates/design/components/`, and a `COMPONENTS` row in `openlibrary/plugins/openlibrary/design.py`.
- Copies the surrounding file's legacy pattern where it conflicts with the above. Only the touched declaration needs to comply; don't ask for whole-file migrations.
