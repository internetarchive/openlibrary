# CSS

Conventions and workflow for writing CSS in Open Library. CSS source lives in `static/css/`, compiled via webpack to `static/build/css/`.

## Naming: BEM

Use BEM (Block Element Modifier) for class names in templates and global styles. **BEM is not required** for Lit web components or Vue components — they have built-in CSS encapsulation (Shadow DOM and `<style scoped>` respectively).

```css
/* Block */
.book-card { }

/* Element (part of the block) */
.book-card__title { }
.book-card__cover { }

/* Modifier (variation of block or element) */
.book-card--featured { }
.book-card__title--large { }
```

## Selector Rules

**Use explicit classes, not bare elements.** Bare element selectors affect every instance globally.

```css
/* Bad — affects every paragraph */
p { margin-bottom: 1rem; }

/* Good — scoped to context */
.book-description__text { margin-bottom: 1em; }
```

**Avoid IDs for styling.** IDs have high specificity and are meant for JavaScript hooks or anchor links, not styling.

**Keep selectors as flat as possible.** Deep nesting makes selectors hard to find and override. That said, sometimes nesting is necessary to win a specificity war with legacy CSS — that's fine, just don't nest more than you need to.

```css
/* Avoid — unnecessarily deep */
.book-list .book-card .book-card__title { }

/* Prefer — flat when possible */
.book-card__title { }

/* Acceptable — nesting to override legacy styles */
.book-card .book-card__title { }
```

## Spacing and Margins

Use only bottom margins for vertical spacing, never top margins. One-directional margins keep layout predictable and avoid margin-collapse surprises.

## Design Tokens

Always use semantic tokens instead of hardcoded values. Stylelint will reject raw hex colors, named colors, and hardcoded values for `font-family`, `background-color`, `z-index`, and `color`.

```css
/* Good — semantic token */
.my-card { border-radius: var(--border-radius-card); }

/* Bad — primitive token */
.my-card { border-radius: var(--border-radius-lg); }

/* Bad — hardcoded */
.my-card { border-radius: 8px; }
```

If no semantic token exists for your use case, create one in the appropriate file under `static/css/tokens/` rather than reaching for a primitive or hardcoded value. See the [Design Token Guide](design.md#design-tokens) for the two-tier system.

## Connecting CSS to Templates

Page-specific CSS files are named `page-*.css` (e.g., `page-home.css`, `page-book.css`). Templates declare which CSS file to load via `putctx()`:

```python
$putctx("cssfile", "page-book")
```

This passes the value up to `site.html`, which loads the corresponding stylesheet in `<head>`.

## Bundle Size Limits

CSS on the critical rendering path has strict size limits. If you see:

```
FAIL static/build/page-plain.css: 18.81KB > maxSize 18.8KB (gzip)
```

Your changes exceeded the CSS payload limit. Options:

- Remove unused styles to make room.
- Move styles into a JavaScript entrypoint file (e.g., `<name>--js.css`) loaded via JS, which has a higher bundlesize threshold. This takes the styles off the critical path.

## Browser Support

Firefox and Chromium-based browsers on desktop and mobile (iOS and Android).
