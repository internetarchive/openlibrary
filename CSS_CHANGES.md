# CSS Changes: LESS Removal & Native CSS Migration

This document covers what changed, what developers need to do after merging, and how to write styles going forward.

---

## What changed

LESS has been fully removed from the project. All stylesheets are now native CSS using CSS custom properties (`var(--token)`). The build pipeline uses webpack's `css-loader` to resolve `@import` statements and `css-minimizer-webpack-plugin` to minify output.

### Removed

- **npm packages:** `less`, `less-loader`, `less-plugin-clean-css`, `postcss-less`
- **All `.less` files** (components, entry points, variables, legacy files)
- **`scripts/generate-css-custom-properties.js`** (token generation script)
- **`static/css/less/` directory** (LESS variable source files)

### Added / Changed

- **`static/css/tokens/`** — 7 CSS files defining design tokens (replaces `less/` variable files)
- **`static/css/tokens.css`** — barrel file that `@import`s all token files, compiled by webpack
- **`static/css/page-*.css`** — all 15 entry points, now native CSS
- **`static/css/components/*.css`** — all ~106 components, now native CSS
- **`webpack.config.css.js`** — LESS rule removed, tokens entry added
- **`webpack.config.js`** — LESS rule removed
- **`.stylelintrc.json`** — `postcss-less` custom syntax removed
- **`package.json`** — lint scripts target `static/` and `openlibrary/` CSS, LESS deps removed
- **`.stylelintignore`** — updated to exclude `vendor/` submodules, `static/css/lib/`, generated token files, and build output

### Lint cleanup

All CSS files now pass `npm run lint:css` with zero errors. Changes made:

- **Prettier formatting** — long selectors and property values auto-wrapped to comply with line-length rules. These are source-only whitespace changes; the minified build output is identical.
- **Raw z-index values replaced with tokens** — e.g. `z-index: 3` → `z-index: var(--z-index-level-3)`. The token values are identical to the raw values they replace (`--z-index-level-1: 1`, `--z-index-level-2: 2`, `--z-index-level-3: 3`, `--z-index-level-16: 99999`). Affected files: `list-follow.css`, `list-showcase.css`, `manage-covers.css`, `rating-form.css`.
- **Selector reordering in `list-showcase.css`** — moved `.list-card` base styles before `.list-showcase .list-card` to satisfy the `no-descending-specificity` rule. No property overlap between these selectors, so cascade behavior is unchanged.
- **Specificity disable comments** — added `stylelint-disable` comments to pre-existing high-specificity selectors in `language.css`, `pd-dashboard.css`, and `read-statuses.css`. No code changes; these are selectors that legitimately need their specificity.
- **Lint scope** — `lint:css` and `lint-fix:css` globs changed from `./**/*.css` to `"static/**/*.css" "openlibrary/**/*.css"` to exclude `vendor/` submodule CSS (infogami, wmd) and third-party library files (`static/css/lib/`) from linting.

### Visual impact

**None.** All changes are either:
- Source formatting only (minified output unchanged)
- Token swaps with identical values (e.g. `3` → `var(--z-index-level-3)` where the token equals `3`)
- Selector reordering where specificity already determines winner (no cascade change)
- Lint comments added to existing selectors (no code change)

---

## Getting your local environment running

After pulling or merging this branch:

```bash
# 1. Install updated dependencies (removes LESS packages, updates lockfile)
npm install

# 2. Rebuild CSS
make css

# 3. Verify the build
ls static/build/css/tokens.css    # should exist (~6 KB)
ls static/build/css/page-user.css # should exist
```

If using Docker:

```bash
docker compose run --rm home npm install --no-audit
docker compose run --rm home make css
```

That's it. The build commands (`make css`, `npm run watch:css`, `npm run watch`) work exactly as before.

### Common issues

| Problem | Fix |
|---------|-----|
| `Module not found: Error: Can't resolve 'less-loader'` | Run `npm install` to remove stale LESS packages |
| Missing `static/build/css/tokens.css` | Run `make css` — tokens are now built by webpack |
| Stylelint errors about unknown syntax | Run `npm install` — `postcss-less` has been removed from `.stylelintrc.json` |
| Stylelint errors in vendor/submodule CSS | Already fixed — lint now scopes to `static/` and `openlibrary/` only |

---

## How to write styles

### Use CSS custom properties for all design tokens

```css
/* Correct */
color: var(--primary-blue);
font-size: var(--font-size-label-large);
border-radius: var(--border-radius-card);

/* Incorrect — do not use raw values for tokenized properties */
color: hsl(202, 96%, 37%);
font-size: 14px;
```

Available tokens are defined in `static/css/tokens/` and organized into:

| File | Contents |
|------|----------|
| `border-radius.css` | Primitives (`--border-radius-sm` etc.) and semantic tokens (`--border-radius-card` etc.) |
| `borders.css` | Border widths, complete border styles, focus ring |
| `breakpoints.css` | Responsive breakpoints (reference only — see note below) |
| `colors.css` | All color tokens organized by hue |
| `font-families.css` | Font stacks, semantic roles, font sizes |
| `line-heights.css` | Primitives and semantic tokens with usage notes |
| `z-index.css` | Z-index scale |

### Breakpoints must be hardcoded in `@media` queries

CSS custom properties **do not work** in `@media` queries. Hardcode the value and add a comment:

```css
/* Correct */
@media (min-width: 768px) { /* --width-breakpoint-tablet */
  .my-component { ... }
}

/* Incorrect — this does NOT work */
@media (min-width: var(--width-breakpoint-tablet)) {
  .my-component { ... }
}
```

Breakpoint values:

| Token | Value |
|-------|-------|
| `--width-breakpoint-mobile-s` | `375px` |
| `--width-breakpoint-mobile-m` | `425px` |
| `--width-breakpoint-mobile` | `450px` |
| `--width-breakpoint-tablet` | `768px` |
| `--width-breakpoint-desktop` | `960px` |

### Do not use CSS nesting

All selectors must be flat. This ensures consistent specificity behavior.

```css
/* Correct */
.my-component { ... }
.my-component:hover { ... }
.my-component--active { ... }
.my-component .child { ... }

/* Incorrect — do not nest */
.my-component {
  &:hover { ... }
  &--active { ... }
  .child { ... }
}
```

### Use `/* */` comments only

CSS does not support `//` comments. They won't cause build errors, but the text will appear in the output.

```css
/* Correct */
/* This is a comment */

/* Incorrect */
// This is not a valid CSS comment
```

### Adding a new component stylesheet

1. Create `static/css/components/my-component.css`
2. Use `var(--token)` for all tokenized values
3. Add `@import "components/my-component.css";` to the relevant `page-*.css` entry point(s)
4. Run `make css` to verify

### Adding a new design token

1. Add the custom property to the appropriate file in `static/css/tokens/`
2. Run `make css` — webpack will rebuild `tokens.css`
3. Use `var(--my-new-token)` in component CSS

### Responsive component stylesheets

For component styles that only apply at certain breakpoints, use media-conditioned imports at the top-level of a page entry point:

```css
/* In page-book.css */
@import "components/work--tablet.css" only screen and (min-width: 768px);
@import "components/header-bar--desktop.css" all and (min-width: 960px);
```

This tells css-loader to wrap the imported content inside the specified `@media` block.

---

## Testing plan

### Automated checks

Run these commands and verify they all pass:

```bash
# Build CSS — must complete with no errors
make css

# Build JS — must complete (the jquery.wmd.js error is pre-existing, not related)
make js

# Jest tests — all 302 tests should pass
npm run test:js

# Lint all (CSS + JS) — must show 0 errors
npm run lint

# Or individually:
npm run lint:css  # scoped to static/ and openlibrary/ directories
npm run lint:js
```

If using Docker:

```bash
docker compose run --rm home make css
docker compose run --rm home make js
docker compose run --rm home npm run test:js
docker compose run --rm home npm run lint
```

### Build output verification

After `make css`, verify these files exist in `static/build/css/`:

```bash
ls -la static/build/css/
```

Expected files (16 total):

| File | Expected size |
|------|--------------|
| `tokens.css` | ~6 KB |
| `page-user.css` | ~120 KB |
| `page-admin.css` | ~130 KB |
| `page-book.css` | ~100 KB |
| `page-home.css` | ~29 KB |
| `page-subject.css` | ~62 KB |
| `page-signup.css` | ~30 KB |
| `page-team.css` | ~26 KB |
| `page-edit.css` | ~97 KB |
| `page-form.css` | ~97 KB |
| `page-plain.css` | ~94 KB |
| `page-lists.css` | ~120 KB |
| `page-list-edit.css` | ~105 KB |
| `page-design.css` | ~85 KB |
| `page-dev.css` | ~0.5 KB |
| `page-book-widget.css` | ~1 KB |

Verify no unresolved `@import` statements in the output:

```bash
grep -c "@import" static/build/css/*.css
# Every file should show 0
```

### Visual QA

Every page type should be visually checked since all CSS was mechanically converted. Open each page and verify that colors, layout, spacing, fonts, hover states, and responsive breakpoints all look correct.

| Page | URL | Entry point | What to check |
|------|-----|-------------|---------------|
| Homepage | `/` | `page-home` | Hero banner, book carousels, header/footer |
| Book/Work | `/works/OL3513417W` | `page-book` | Cover image, read panel, edition list, ratings |
| Edition | `/books/OL9737752M` | `page-book` | Edition details, cover, borrow button |
| Search results | `/search?q=test` | `page-user` | Result cards, pagination, facets |
| Author | `/authors/OL34184A` | `page-user` | Author photo, works list |
| Subject | `/subjects/fiction` | `page-subject` | Book grid, subject header |
| My Books | `/people/openlibrary` | `page-user` | Shelves, reading log, menu |
| Lists | `/people/openlibrary/lists` | `page-lists` | List cards, showcase |
| List Edit | A list edit page | `page-list-edit` | Form, seed autocomplete |
| Admin | `/admin` | `page-admin` | Admin tables, dashboard |
| Sign Up | `/account/create` | `page-signup` | Form inputs, hero panel, error states |
| Login | `/account/login` | `page-signup` | Form layout |
| Edit page | `/books/OL9737752M/edit` | `page-edit` | Edit form, toolbar |
| Team page | `/about/team` | `page-team` | Team member cards |
| Design page | `/dev/design` (if enabled) | `page-design` | Pattern library |

**For each page, check:**

- [ ] Colors are correct (especially hover/focus states)
- [ ] Font sizes and families match expectations
- [ ] Spacing and layout are unchanged
- [ ] Responsive behavior at mobile (< 450px), tablet (768px), and desktop (960px)
- [ ] Interactive states work (hover, focus, active, disabled)
- [ ] Header bar and footer render correctly
- [ ] No visual glitches or missing styles

### Responsive breakpoint testing

Resize the browser or use DevTools device mode to verify these breakpoints:

1. **Mobile** (< 768px): Header collapses to mobile nav, content is single-column
2. **Tablet** (768px–959px): Header expands, some two-column layouts appear
3. **Desktop** (960px+): Full desktop layout with sidebars

Pay special attention to the header bar, as it has the most breakpoint-dependent styles.
