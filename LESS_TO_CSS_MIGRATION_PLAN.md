# LESS to Native CSS Migration Plan

> **Goal:** Fully remove LESS from the Open Library codebase and use only native CSS.
> **Audience:** Junior engineers new to the codebase.
> **Status:** Infrastructure is ready. One component (`link-box`) has been migrated as a proof-of-concept. ~139 LESS files remain.

---

## Table of Contents

1. [Background & Context](#1-background--context)
2. [What Has Already Been Done](#2-what-has-already-been-done)
3. [Architecture Overview](#3-architecture-overview)
4. [Migration Strategy](#4-migration-strategy)
5. [How to Migrate a Component (Step-by-Step)](#5-how-to-migrate-a-component-step-by-step)
6. [LESS Feature → CSS Equivalent Cheat Sheet](#6-less-feature--css-equivalent-cheat-sheet)
7. [Phase 1 — Migrate Component Files](#phase-1--migrate-component-files)
8. [Phase 2 — Migrate Page Entry Points](#phase-2--migrate-page-entry-points)
9. [Phase 3 — Migrate JS-Bundled Stylesheets](#phase-3--migrate-js-bundled-stylesheets)
10. [Phase 4 — Clean Up Infrastructure](#phase-4--clean-up-infrastructure)
11. [Phase 5 — Remove LESS Entirely](#phase-5--remove-less-entirely)
12. [Known Hacks & Gotchas](#known-hacks--gotchas)
13. [Testing & QA](#testing--qa)
14. [File Inventory](#file-inventory)

---

## 1. Background & Context

Open Library currently uses [LESS](https://lesscss.org/) as a CSS preprocessor. LESS provides features like variables (`@color`), nesting, color functions (`darken()`, `lighten()`), and mixins. Modern CSS now supports most of these features natively:

- **Variables** → CSS Custom Properties (`var(--color)`)
- **Nesting** → [CSS Nesting](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_nesting) (supported in all evergreen browsers) — **but see the gotchas section before using this**
- **Color functions** → `color-mix()`, `hsl()` manipulation, or pre-computed values

By removing LESS we:
- Eliminate a build-time compilation step
- Remove 3 npm dependencies (`less`, `less-loader`, `less-plugin-clean-css`)
- Let engineers write standard CSS that works in any tool
- Simplify the webpack configuration

### Key Files You Should Know

| File | What It Does |
|------|-------------|
| `webpack.config.css.js` | Builds page stylesheets. Has rules for both `.less` and `.css` files. |
| `webpack.config.js` | Builds JavaScript. Also has a LESS rule for `js-all.less` and `SelectionManager.less`. |
| `scripts/generate-css-custom-properties.js` | Reads LESS variable files → outputs `generated-custom-properties.css` with CSS custom properties. |
| `static/css/less/generated-custom-properties.css` | Auto-generated file with 195 CSS custom properties (design tokens). Loaded in `<head>` for all pages. |
| `openlibrary/templates/site/head.html` | Main HTML template. Loads the custom properties CSS and the page-specific compiled CSS. |
| `static/css/page-*.less` | Entry point stylesheets. Each one corresponds to a page type (home, book, user, etc). |
| `static/css/components/*.less` | Individual component stylesheets (~106 files). |
| `static/css/less/*.less` | Design token definitions (colors, breakpoints, fonts, etc). |
| `.stylelintrc.json` | Linting config. Currently set to `postcss-less` syntax. |
| `package.json` | Contains LESS-related dependencies and lint scripts that target `*.less`. |

---

## 2. What Has Already Been Done

- **Webpack CSS pipeline**: `webpack.config.css.js` supports both `.less` and `.css` entry points. CSS files take precedence when both exist for the same page name.
- **CSS Custom Properties**: All 195 LESS variables have been converted to CSS custom properties in `static/css/less/generated-custom-properties.css`. This file is loaded separately in `<head>` for caching.
- **Proof of concept**: `link-box.less` was migrated to `link-box.css`. LESS files that import it use `@import (inline) "components/link-box.css"` to paste the CSS verbatim.
- **CSS Minimizer**: `css-minimizer-webpack-plugin` is installed for minifying native CSS files.

---

## 3. Architecture Overview

### How styles get to the browser today

```
static/css/page-book.less          (entry point)
  ├── @import "less/index.less"     (LESS variables: @primary-blue, etc.)
  ├── @import "base/index.less"     (base styles)
  ├── @import "layout/index.less"   (layout rules)
  └── @import "components/X.less"   (component styles)
        └── @import "less/index.less" (each component re-imports variables)

  ↓  webpack + less-loader + clean-css

static/build/css/page-book.css     (compiled, minified, served to browser)
```

There is also a **JS-bundled** stylesheet path:

```
openlibrary/plugins/openlibrary/js/index.js
  └── import 'static/css/js-all.less'
        └── @import components for JS-only styles

  ↓  webpack + style-loader + less-loader

Injected into <style> tags at runtime (not a separate CSS file)
```

And one more outlier:

```
openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.js
  └── import './SelectionManager.less'

  ↓  webpack + style-loader + less-loader

Injected into <style> tags at runtime
```

### How styles will work after migration

```
static/css/page-book.css           (native CSS entry point)
  ├── @import "base/index.css"
  ├── @import "layout/index.css"
  └── @import "components/X.css"
        └── Uses var(--primary-blue) etc. (resolved from :root custom properties)

  ↓  webpack css-loader + css-minimizer-webpack-plugin

static/build/css/page-book.css     (minified, served to browser)
```

The `generated-custom-properties.css` is loaded as a separate `<link>` in `<head>` and provides all `var(--token)` values globally.

---

## 4. Migration Strategy

We use a **bottom-up, component-by-component** approach:

1. **Migrate individual component `.less` files to `.css`** — one at a time, in any order.
2. **Update parent files** that import the component to use `@import (inline)` for the new `.css` file (while they are still `.less`).
3. **Once ALL components imported by a page entry are `.css`**, migrate the page entry point itself from `.less` to `.css`.
4. **Once ALL page entries are `.css`**, remove the LESS pipeline entirely.

This approach lets us ship incremental PRs that can be individually reviewed and tested.

### Rules

- **One component per PR.** Keep PRs small and easy to review.
- **Always visually verify** the page(s) that use the component after migration.
- **Do not change any visual behavior.** This is a mechanical translation, not a redesign.
- **Run the CSS lint** after each migration: `npm run lint:css`.

---

## 5. How to Migrate a Component (Step-by-Step)

Let's walk through migrating a component using `buttonCta.less` as an example.

### Step 1: Read the LESS file and identify what LESS features it uses

Open `static/css/components/buttonCta.less` and look for:

- `@variable` references → will become `var(--variable)`
- `@import` statements → will change syntax
- `&` nesting (parent selectors) → will be flattened into explicit selectors
- Color functions (`darken()`, `lighten()`, `fade()`, `mix()`, `desaturate()`) → see cheat sheet below
- LESS-specific `//` comments → change to `/* */` (CSS does not support `//` comments)

### Step 2: Create the `.css` file

Create `static/css/components/buttonCta.css`. Copy the content from the `.less` file and begin converting.

**Variable conversion:**
```less
/* BEFORE (LESS) */
color: @white;
font-size: @font-size-label-large;
```
```css
/* AFTER (CSS) */
color: var(--white);
font-size: var(--font-size-label-large);
```

**Nesting conversion (flatten it):**
```less
/* BEFORE (LESS) */
.cta-btn {
  &:hover {
    color: @red;
  }
  &--primary {
    background: @primary-blue;
  }
  .btn-icon {
    width: 22px;
  }
}
```
```css
/* AFTER (CSS) */
.cta-btn:hover {
  color: var(--red);
}
.cta-btn--primary {
  background: var(--primary-blue);
}
.cta-btn .btn-icon {
  width: 22px;
}
```

**Color function conversion:**
```less
/* BEFORE (LESS) */
background-color: darken(@primary-blue, 20%);
```
```css
/* AFTER (CSS) */
background-color: hsl(202, 96%, 17%);
```
See the [cheat sheet below](#6-less-feature--css-equivalent-cheat-sheet) for how to compute these.

**Comment conversion:**
```less
// This is a LESS comment
```
```css
/* This is a CSS comment */
```

**Import removal:**
Remove any `@import "../less/index.less"` lines. The CSS custom properties are loaded globally by `<head>`, so your `.css` file does not need to import them.

### Step 3: Update all parent files that import this component

Find every file that imports the old `.less` file:

```bash
grep -r "buttonCta.less" static/css/
```

In each parent file, change the import:

```less
/* BEFORE */
@import (less) "components/buttonCta.less";
```
```less
/* AFTER (while the parent is still .less) */
@import (inline) "components/buttonCta.css";
```

The `(inline)` keyword tells LESS to paste the CSS content verbatim without trying to process it as LESS. This is critical — without it, LESS will choke on `var(--foo)` syntax because `--` looks like LESS syntax errors.

### Step 4: Delete the old `.less` file

```bash
rm static/css/components/buttonCta.less
```

### Step 5: Verify

1. Run the build: `make css`
2. Open the pages that include this component in a browser
3. Visually compare — nothing should change
4. Run the linter: `npm run lint:css`

---

## 6. LESS Feature → CSS Equivalent Cheat Sheet

### Variables

| LESS | CSS |
|------|-----|
| `@primary-blue` | `var(--primary-blue)` |
| `@font-size-label-large` | `var(--font-size-label-large)` |
| `@width-breakpoint-tablet` | `768px` (hardcode in media queries — see gotcha below) |

### Color Functions

LESS color functions need to be converted to either pre-computed values or `color-mix()`.

#### `darken(@color, amount)`

Darken reduces the lightness in HSL. Look up the base color's HSL value and reduce the L component.

```less
/* LESS */
darken(@primary-blue, 20%)
/* @primary-blue is hsl(202, 96%, 37%) */
/* 37% - 20% = 17% */
```
```css
/* CSS — pre-computed */
hsl(202, 96%, 17%)
```

**Alternative**: Define a new custom property for the darkened value:
```css
/* In generated-custom-properties.css or a new tokens file */
--primary-blue-dark: hsl(202, 96%, 17%);
```

#### `lighten(@color, amount)`

Same as darken but increase the L value.

```less
lighten(@link-blue, 67%)
/* @link-blue is hsl(202, 96%, 28%) */
/* 28% + 67% = 95% (capped at 100%) */
```
```css
hsl(202, 96%, 95%)
```

#### `fade(@color, amount)`

`fade()` in LESS sets the alpha/opacity of a color. Convert to `hsla()` or `color-mix()`.

```less
fade(@black, 25%)
```
```css
/* Option A: hsla */
hsla(0, 0%, 0%, 0.25)

/* Option B: color-mix (modern CSS) */
color-mix(in srgb, var(--black) 25%, transparent)
```

We recommend **Option A (`hsla`)** for simplicity and browser support — just look up the HSL values from `colors.less` and add the alpha channel.

#### `mix(@color1, @color2, weight)`

```less
mix(@beige, @white, 75%)
```
```css
color-mix(in srgb, var(--beige) 75%, var(--white))
```

`color-mix()` is supported in all evergreen browsers. This is a direct 1:1 replacement.

#### `desaturate(@color, amount)`

Reduce the S (saturation) component in HSL.

```less
desaturate(@link-blue, 56%)
/* @link-blue is hsl(202, 96%, 28%) */
/* 96% - 56% = 40% */
```
```css
hsl(202, 40%, 28%)
```

#### Chained functions

Some LESS expressions chain multiple functions:

```less
fade(lighten(desaturate(@link-blue, 56%), 67%), 50%)
```

Work from inside out:
1. `desaturate(@link-blue, 56%)` → `hsl(202, 40%, 28%)`
2. `lighten(..., 67%)` → `hsl(202, 40%, 95%)`
3. `fade(..., 50%)` → `hsla(202, 40%, 95%, 0.5)`

Final CSS: `hsla(202, 40%, 95%, 0.5)`

### Nesting

LESS allows nesting selectors. CSS Nesting is now supported in browsers, **but we are NOT using CSS Nesting in this migration**. Instead, flatten all nesting into explicit selectors. This is the safest approach and avoids subtle specificity differences between LESS nesting and CSS nesting.

| LESS | CSS (flattened) |
|------|----------------|
| `.parent { .child { } }` | `.parent .child { }` |
| `.parent { &:hover { } }` | `.parent:hover { }` |
| `.parent { &--modifier { } }` | `.parent--modifier { }` |
| `.parent { &__element { } }` | `.parent__element { }` |
| `.parent { > .child { } }` | `.parent > .child { }` |
| `.parent { &.other { } }` | `.parent.other { }` |
| `.parent { & + & { } }` | `.parent + .parent { }` |

### `@media` with variable breakpoints

LESS allows `@media (min-width: @width-breakpoint-tablet)` because it resolves the variable at compile time. **CSS custom properties do NOT work inside `@media` queries.**

```less
/* LESS — works because @variable is compile-time */
@media (min-width: @width-breakpoint-tablet) { ... }
```
```css
/* CSS — must hardcode the value */
@media (min-width: 768px) { ... }
```

The breakpoint values are:
| LESS Variable | Value |
|--------------|-------|
| `@width-breakpoint-mobile-s` | `375px` |
| `@width-breakpoint-mobile-m` | `425px` |
| `@width-breakpoint-mobile` | `450px` |
| `@width-breakpoint-tablet` | `768px` |
| `@width-breakpoint-desktop` | `960px` |

**Add a comment** next to each hardcoded value so future developers know where it came from:

```css
/* --width-breakpoint-tablet */
@media (min-width: 768px) { ... }
```

### Imports

| LESS context | CSS equivalent |
|-------------|---------------|
| `@import (less) "components/X.less"` (in a `.less` parent) | `@import (inline) "components/X.css"` (while parent is still `.less`) |
| `@import (less) "components/X.less"` (in a `.css` parent) | `@import "components/X.css"` (standard CSS import) |
| `@import "../less/index.less"` (variable import) | **Delete it.** CSS custom properties are loaded globally. |

### `@import` inside `@media` blocks (LESS-specific pattern)

Several files import components conditionally inside `@media` blocks:

```less
@media only screen and (min-width: @width-breakpoint-tablet) {
  @import (less) "components/edit-toolbar--tablet.less";
}
```

LESS handles this by wrapping all the imported content inside the `@media` rule. **CSS `@import` does not work inside `@media` blocks.** You have two options:

**Option A (Recommended): Inline the content.**
Move the contents of `edit-toolbar--tablet.less` directly into the parent file, wrapped in the `@media` block:

```css
/* --width-breakpoint-tablet */
@media only screen and (min-width: 768px) {
  /* Contents of edit-toolbar--tablet.css pasted here */
  .edit-toolbar { ... }
}
```

**Option B: Use `@import` with a media condition.**
CSS supports `@import url("file.css") (min-width: 768px)` but only at the top of the file, before any other rules. This is awkward and adds an extra HTTP request in dev, so Option A is preferred.

---

## Phase 1 — Migrate Component Files

Migrate all `~106 files` in `static/css/components/`. Order doesn't matter, but prioritize:

1. **Leaf components first** (components that don't import other components)
2. **Components shared across many pages** (so progress unblocks page entry migration)
3. **Simple components** (few LESS features) before complex ones

### Components with Color Functions (Harder)

These files use `darken()`, `lighten()`, `fade()`, `mix()`, or `desaturate()` and require extra care:

| File | Functions Used |
|------|---------------|
| `buttonCta.less` | `darken`, `lighten`, `desaturate` |
| `nav-bar.less` | `darken` |
| `notes-view.less` | `darken` |
| `carousel.less` | `fade` |
| `editions.less` | `mix` |
| `header-bar.less` | `fade` |
| `list-follow.less` | `fade` |
| `list-showcase.less` | `fade` |
| `read-panel.less` | `fade`, `lighten`, `desaturate` |
| `reading-goal.less` | `fade` |
| `search-result-item.less` | `fade` |
| `page-signup.less` (entry) | `fade` |
| `page-admin.less` (entry) | `desaturate` |
| `base/common.less` | `fade` |

All other components only use variables and nesting — straightforward conversions.

### `@import` inside `@media` blocks (needs special handling)

These files conditionally import inside `@media` blocks:

| Parent File | Imported File | Media Condition |
|------------|--------------|----------------|
| `page-book.less` | `edit-toolbar--tablet.less` | `min-width: 768px` |
| `components/work.less` | `work--tablet.less` | `min-width: 768px` |
| `components/header.less` | `header-bar--tablet.less` | `min-width: 768px` |
| `components/header.less` | `page-banner--tablet.less` | `min-width: 768px` |
| `components/header.less` | `header-bar--desktop.less` | `min-width: 960px` |

When migrating these, use **Option A** from the cheat sheet: inline the content directly inside the `@media` block.

### Migration checklist per component

- [ ] Read the `.less` file and list all LESS features used
- [ ] Create `.css` file with converted content
- [ ] Replace `@variables` with `var(--variables)`
- [ ] Flatten all nesting
- [ ] Convert color functions to pre-computed values
- [ ] Convert `//` comments to `/* */`
- [ ] Remove `@import "../less/index.less"` (not needed)
- [ ] Update all parent files: change `@import (less) "X.less"` → `@import (inline) "X.css"`
- [ ] Delete the `.less` file
- [ ] Run `make css` — build succeeds
- [ ] Visually verify on affected pages
- [ ] Run `npm run lint:css` — no new errors

---

## Phase 2 — Migrate Page Entry Points

Once **all components** imported by a page entry are `.css`, convert the page entry itself.

There are **15 page entry points** plus `js-all.less`:

| Entry Point | Component Count | Notes |
|------------|----------------|-------|
| `page-plain.less` | 4 imports | Smallest, good first candidate |
| `page-design.less` | 2 imports | Very small |
| `page-book-widget.less` | 3 imports | Small |
| `page-form.less` | 3 imports | Small |
| `page-dev.less` | 1 import | Tiny (loaded conditionally for dev feature flag) |
| `page-lists.less` | 4 imports | Small |
| `page-list-edit.less` | 5 imports | Small |
| `page-home.less` | 8 imports | Medium |
| `page-admin.less` | 7 imports | Medium, has inline styles + `desaturate()` |
| `page-team.less` | 7 imports | Medium |
| `page-signup.less` | 10 imports | Has inline styles + `fade()` |
| `page-edit.less` | 4 imports | Medium (has inline `@media` conditional imports) |
| `page-subject.less` | 14 imports | Large |
| `page-book.less` | 21 imports | Largest, has `@media` conditional imports |
| `page-user.less` | 21 imports | Largest, default page style |

### How to migrate a page entry

When converting `page-home.less` → `page-home.css`:

1. **Create `page-home.css`** with the converted content.
2. Change all imports from `@import (less) "X.less"` or `@import (inline) "X.css"` to plain `@import "X.css"`.
3. Hardcode any `@media` breakpoint variables.
4. Flatten any inline nesting.
5. **Delete `page-home.less`**.
6. Webpack will automatically pick up `page-home.css` instead (CSS takes precedence in the entry discovery).
7. Verify: `make css` and check the page.

---

## Phase 3 — Migrate JS-Bundled Stylesheets

Two stylesheets are loaded via JavaScript `import` statements, not through the CSS webpack pipeline:

### 3a. `js-all.less`

**Location:** `static/css/js-all.less`
**Imported by:** `openlibrary/plugins/openlibrary/js/index.js` (line 6)
**Loaded via:** `webpack.config.js` → `style-loader` (injected as `<style>` tag at runtime)

This file imports ~12 components that only apply when JavaScript is enabled. To migrate:

1. Convert `js-all.less` → `js-all.css` (same process as page entries).
2. Update the import in `index.js`:
   ```js
   // BEFORE
   import '../../../../static/css/js-all.less';
   // AFTER
   import '../../../../static/css/js-all.css';
   ```
3. Update `webpack.config.js` to handle `.css` files (add a CSS rule — see below).
4. The file also has inline LESS at the bottom (`.coverEbook` and `.tools` rules with nesting) — flatten these.

### 3b. `SelectionManager.less`

**Location:** `openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.less`
**Imported by:** `SelectionManager.js` in the same directory
**Loaded via:** `webpack.config.js` → `style-loader`

This is a standalone LESS file with its own local variables (not using the shared design tokens). To migrate:

1. Convert to `SelectionManager.css` — replace `@variable` definitions with CSS custom properties or just hardcode the values (they're only used in this one file).
2. Update the import in `SelectionManager.js`:
   ```js
   import './SelectionManager.css';
   ```

### 3c. Update `webpack.config.js` CSS rule

Add a CSS loader rule to `webpack.config.js` so it can handle `.css` imports:

```js
{
    test: /\.css$/,
    use: [
        { loader: 'style-loader' },
        { loader: 'css-loader', options: { url: false } }
    ]
}
```

---

## Phase 4 — Clean Up Infrastructure

Once all LESS files are gone:

### 4a. Design tokens — convert to hand-maintained CSS

The `generated-custom-properties.css` file is currently auto-generated from LESS variable files by `scripts/generate-css-custom-properties.js`. Once LESS is gone:

1. **Copy** the contents of `generated-custom-properties.css` into a new file: `static/css/tokens.css` (or keep the same filename — your choice).
2. **Remove the "DO NOT EDIT" header** and make it a normal, hand-editable file.
3. **Delete** all files in `static/css/less/` (the LESS variable files and `index.less`).
4. **Delete** `scripts/generate-css-custom-properties.js`.
5. **Update the reference in `head.html`** if you renamed the file.

### 4b. Update `webpack.config.css.js`

1. Remove the `.less` rule entirely (lines 57–84).
2. Remove `less-loader` and `less-plugin-clean-css` from the loader chain.
3. Remove the `GenerateCSSVarsPlugin` (the `beforeCompile` hook that runs the generation script).
4. Remove the `glob.sync('./static/css/page-*.less')` line — only scan for `.css`.
5. Remove `less-loader` import at the top if present.

### 4c. Update `webpack.config.js`

1. Remove the `.less` rule (lines 49–65).
2. Ensure the `.css` rule added in Phase 3c is present.

### 4d. Update Stylelint config

In `.stylelintrc.json`:
1. **Remove** `"customSyntax": "postcss-less"` — this is no longer needed.
2. Optionally update rules if any were LESS-specific.

In `package.json`, update lint scripts:
```json
// BEFORE
"lint:css": "stylelint ./**/*.less",
"lint-fix:css": "stylelint --fix ./**/*.less",

// AFTER
"lint:css": "stylelint ./**/*.css",
"lint-fix:css": "stylelint --fix ./**/*.css",
```

You may want to add a `--ignore-pattern` for `node_modules` and `static/build`.

### 4e. Update Makefile

The `css` target currently runs `generate-css-custom-properties.js` before webpack. Remove that line:

```makefile
# BEFORE
css:
	node scripts/generate-css-custom-properties.js
	mkdir -p $(BUILD)/css_new
	...

# AFTER
css:
	mkdir -p $(BUILD)/css_new
	...
```

### 4f. Update Jest config

In `package.json`, the Jest `moduleNameMapper` maps `\.(css|less)$` to a style mock. Update to only match `.css`:

```json
"moduleNameMapper": {
  "\\.(css)$": "<rootDir>/tests/unit/js/styleMock.js"
}
```

---

## Phase 5 — Remove LESS Entirely

### 5a. Remove npm dependencies

```bash
npm uninstall less less-loader less-plugin-clean-css postcss-less
```

### 5b. Verify nothing references LESS

```bash
# Should return no results
grep -r "\.less" static/css/
grep -r "less-loader" webpack.config*.js
grep -r "less" .stylelintrc.json
```

### 5c. Final verification

1. `npm install` (clean install)
2. `make css` — builds successfully
3. `make js` — builds successfully
4. `npm run lint` — passes
5. Full visual QA pass across all page types

---

## Known Hacks & Gotchas

### 1. `@import (inline)` is a transitional hack

During migration, when a parent `.less` file imports a child `.css` file, we use `@import (inline)` which tells LESS to paste the file contents verbatim without parsing. **This only works while the parent is still `.less`.** Once the parent is converted to `.css`, switch to a standard `@import "file.css"`.

This is the core trick that makes incremental migration possible: a LESS file can include raw CSS, and CSS files use standard imports. The two formats can coexist.

### 2. CSS custom properties don't work in `@media` queries

This is a real limitation of CSS. You **cannot** do:

```css
/* THIS DOES NOT WORK */
@media (min-width: var(--width-breakpoint-tablet)) { ... }
```

You must hardcode the pixel value. Always add a comment noting which token the value corresponds to.

If the [CSS Environment Variables](https://drafts.csswg.org/css-env-1/) spec lands in browsers in the future, this could be revisited, but for now, hardcoding is the only option.

### 3. LESS nesting and CSS Nesting have different specificity behavior

LESS nesting is purely syntactic sugar — `& .child` compiles to `.parent .child` with no specificity change. CSS Nesting (using `&`) can sometimes produce different specificity because of how the `:is()` wrapper works internally. **To avoid any surprises, we are flattening all nesting instead of using CSS Nesting.** This is more verbose but guarantees identical behavior.

### 4. `//` comments are invalid in CSS

LESS supports `//` single-line comments. CSS does not. If you forget to convert these, the build won't fail, but the `//` text will appear in the output as-is (a browser will usually ignore it, but it's messy and can cause unexpected behavior). Always convert to `/* */`.

### 5. The `generated-custom-properties.css` lives in the `less/` directory

This is confusing — a `.css` file living in a folder called `less/`. This is an artifact of the migration being in progress. During Phase 4, move/rename the tokens file to a more sensible location like `static/css/tokens.css`.

### 6. Color function pre-computation is manual and error-prone

When converting `darken(@primary-blue, 20%)`, you have to manually look up the HSL values and do the math. Double-check your arithmetic. A useful approach:

1. Open browser DevTools
2. Go to a page where the old LESS-compiled CSS is active
3. Inspect the element that uses the color function
4. Copy the computed color value from DevTools
5. Use that exact value in your CSS

This ensures pixel-perfect color matching.

### 7. `base/common.less` uses `fade()` on an unquoted hex value

Line 53: `background: fade(@beige, 66)`. Note that in LESS, `fade(@beige, 66)` means "set opacity to 66%". The `@beige` variable is `hsl(48, 33%, 83%)`, so the result is `hsla(48, 33%, 83%, 0.66)`.

### 8. Some components re-import `less/index.less` redundantly

Many component files start with `@import "../less/index.less"`. In LESS, this is needed because each file needs access to variables. In CSS, custom properties are globally available via the `:root` declaration in `<head>`, so **all these imports should simply be deleted** — not converted to CSS imports.

### 9. `page-book.less` and `page-user.less` are the most complex

These two files import 21 components each. They should be migrated **last** among the page entries, after you've gotten comfortable with the process on smaller pages.

### 10. `legacy.less` is 1,718 lines of old CSS

This file is marked "DO NOT ADD NEW CSS HERE" and is slowly being decomposed. It imports from `legacy-header.less`, `legacy-tools.less`, `legacy-wmd.less`, etc. Migrating this is straightforward (it mostly uses variables, not complex LESS features) but tedious due to its size. Consider breaking it into smaller pieces as part of the migration, or just do a direct 1:1 conversion.

### 11. `SelectionManager.less` uses local variables, not shared tokens

This file defines its own `@selection-outline`, `@selection-background`, etc. These are NOT in the global design tokens. When converting, either:
- Hardcode the values (simplest, since they're only used in one file)
- Add them to the global custom properties file (if you think they might be reused)

### 12. The `less/` directory `index.less` bundles all variable files

`static/css/less/index.less` just re-exports all the variable files:
```less
@import (less) "breakpoints.less";
@import (less) "colors.less";
...
```
After migration, this file and the entire `less/` directory can be deleted. The `generated-custom-properties.css` (or its renamed successor) replaces all of it.

### 13. `stylelint-declaration-strict-value` enforces token usage

The Stylelint config enforces that `font-family`, `background-color`, `z-index`, and `color` must use variables (not raw values). After migration, this plugin should be updated to check for `var(--token)` usage instead of LESS `@variable` usage. Verify that the plugin supports CSS custom properties.

---

## Testing & QA

### Automated

- `make css` — build must succeed
- `npm run lint:css` — linter must pass
- `npm test` — JS tests must pass (the `styleMock.js` maps catch CSS imports)

### Visual QA Checklist

For each migrated component, check the pages it appears on:

| Page | URL Pattern | Entry Point |
|------|-----------|------------|
| Homepage | `/` | `page-home` |
| Book/Work | `/works/OL*` or `/books/OL*` | `page-book` |
| Author | `/authors/OL*` | `page-user` |
| Search | `/search` | `page-user` |
| Subject | `/subjects/*` | `page-subject` |
| Lists | `/people/*/lists` | `page-lists` |
| List Edit | `/people/*/lists/*/edit` | `page-list-edit` |
| My Books | `/people/*` | `page-user` |
| Admin | `/admin` | `page-admin` |
| Sign Up | `/account/create` | `page-signup` |
| Edit | `/books/OL*/edit` | `page-edit` |

**What to check:**
- Colors are correct (especially hover states and derived colors from `darken`/`lighten`)
- Spacing and layout are unchanged
- Font sizes and families match
- Responsive breakpoints trigger at the same widths
- Interactive states (hover, focus, active, disabled) look right
- No raw `//` comment text visible on the page

---

## File Inventory

### LESS Variable Files (8 files) → Delete after Phase 4
```
static/css/less/
├── index.less
├── border-radius.less
├── borders.less
├── breakpoints.less
├── colors.less
├── font-families.less
├── line-heights.less
├── z-index.less
└── generated-custom-properties.css  ← keep (rename/move)
```

### Page Entry Points (15 files) → Convert in Phase 2
```
static/css/
├── page-admin.less
├── page-book.less
├── page-book-widget.less
├── page-design.less
├── page-dev.less
├── page-edit.less
├── page-form.less
├── page-home.less
├── page-list-edit.less
├── page-lists.less
├── page-plain.less
├── page-signup.less
├── page-subject.less
├── page-team.less
└── page-user.less
```

### JS-Bundled Stylesheets (2 files) → Convert in Phase 3
```
static/css/js-all.less
openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.less
```

### Legacy Files (7 files) → Convert in Phase 1
```
static/css/
├── legacy.less              (1,718 lines)
├── legacy-borrowTable-adminUser.less
├── legacy-datatables.less
├── legacy-header.less
├── legacy-jquery-ui.less
├── legacy-tools.less
└── legacy-wmd.less
```

### Base & Layout Files (8 files) → Convert in Phase 1
```
static/css/base/
├── index.less
├── common.less
├── dl.less
├── headings.less
├── helpers-common.less
└── helpers-misc.less

static/css/layout/
├── index.less
└── v2.less
```

### Component Files (~106 files) → Convert in Phase 1
```
static/css/components/
├── link-box.css              ← ALREADY MIGRATED
├── buttonBtn.less
├── buttonCta.less
├── carousel.less
├── ... (103 more files)
```

### Files to Delete After Full Migration
```
scripts/generate-css-custom-properties.js
static/css/less/*.less (all 8 files)
```

### Dependencies to Remove
```
less
less-loader
less-plugin-clean-css
postcss-less
```
