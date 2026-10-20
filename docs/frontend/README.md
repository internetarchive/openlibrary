# Front End

> **Status:** partial
> **Sources:** `raw/openlibrary-docs-ai/css.md`, `raw/openlibrary-docs-ai/design.md`, `raw/openlibrary-docs-ai/web-components.md`
> **Last ingested:** 2026-06-27

Open Library's frontend is a hybrid: server-rendered Templetor (`.html`) and Jinja (`.jinja`) templates with a Lit web component layer for interactive elements, Vue for a few specialized tools, and vanilla JS for one-off enhancements. CSS is written to BEM conventions and built via webpack into `static/build/css/`. Design tokens are two-tier (primitives → semantic). Accessibility is built into the component standards.

---

## How It Works

### Template layers

| Layer | Where | When to use |
|-------|-------|-------------|
| Templetor `.html` | `openlibrary/templates/` | Legacy; maintained for backward compat |
| Jinja `.jinja` | `openlibrary/templates/` | **Preferred for new work** |
| Lit web components | `openlibrary/components/lit/` | Interactive, reusable, encapsulated UI |
| Vue | `openlibrary/plugins/openlibrary/js/` | Librarian merge UI, reading stats, library explorer only (see [[library-explorer]]) |
| Vanilla JS | `openlibrary/plugins/openlibrary/js/` | One-off page enhancements with no encapsulation need |

### CSS pipeline

CSS source lives in `static/css/`, compiled via webpack to `static/build/css/`. Page-specific CSS files are named `page-*.css`. Templates declare which to load via:

```python
$putctx("cssfile", "page-book")
```

`site.html` picks this up and loads the stylesheet in `<head>`.

### Lit component pipeline

Components live in `openlibrary/components/lit/`. The entry point `index.js` re-exports every component (running `customElements.define()` as a side effect) and is built as `ol-components.js`, loaded site-wide from `openlibrary/templates/site/footer.html`.

Build/watch:
```bash
npm run watch:lit-components   # dev mode
make lit-components            # one-off build
```

### Vue component pipeline

Every top-level `.vue` file directly in `openlibrary/components/` (not its subdirectories — those are internal sub-components imported by a top-level one) is auto-discovered and built as its own standalone custom element, one per file: `BarcodeScanner.vue` → `<ol-barcode-scanner>`, `LibraryExplorer.vue` → `<ol-library-explorer>`, etc. Config: `openlibrary/components/vite.config.mjs` (Vite, not webpack, for this pipeline — webpack is CSS/Lit's build tool, not Vue's).

Two things this config does that aren't obvious from a default Vite+Vue setup:
- `vue({ customElement: true })` — compiles each component as a genuine custom element (Shadow DOM, no Vue app-mount boilerplate needed in the page), not a normal Vue SPA component.
- `template: { compilerOptions: { isCustomElement: tag => tag.startsWith('ol-') } }` — lets a Vue template use the site-wide Lit component bundle's tags (`<ol-toggle>`, `<ol-select-popover>`, etc. — already globally registered by the Lit pipeline above) directly, without Vue trying to resolve them as unregistered Vue components.

Build:
```bash
make components   # via docker compose run --rm home make components — no dev/watch mode documented for this pipeline
```

---

## Design Tokens (Two-Tier System)

Token files in `static/css/tokens/`:

| File | Contents |
|------|---------|
| `colors.css` | Color primitives + semantic color tokens |
| `spacing.css` | Spacing scale |
| `border-radius.css` | Border radius primitives + semantic tokens |
| `typography.css` | Font families, sizes, weights |

**Tier 1 — Primitives** (raw values, rarely used directly):
```css
--blue-500: hsl(210, 80%, 50%);
--border-radius-lg: 8px;
```

**Tier 2 — Semantic tokens** (describe purpose, not appearance):
```css
--color-link: var(--blue-600);
--border-radius-card: var(--border-radius-lg);
```

**Always use semantic tokens.** Stylelint will reject raw hex colors, named colors, and hardcoded values for `font-family`, `background-color`, `z-index`, and `color`. If no semantic token exists, create one in the appropriate token file.

CSS custom properties inherit through the Shadow DOM boundary — tokens work inside Lit `static styles` blocks without extra wiring.

---

## How It Is Used

### Adding a Lit web component

1. Create `openlibrary/components/lit/OlMyWidget.js`
2. Add export to `openlibrary/components/lit/index.js`
3. Add JSDoc (`@prop`, `@fires`, `@slot`, `@cssprop`, `@csspart`)
4. Regenerate manifest: `npm run build-assets:lit-manifest` → commit `custom-elements.json`
5. Add demo `<section>` to `openlibrary/templates/design.html`
6. Verify at http://localhost:8080/developers/design

Tag names: `ol-<name>` (kebab-case). Class names: `OlMyWidget` (PascalCase, `Ol` prefix). Register at bottom of file: `customElements.define('ol-my-widget', OlMyWidget)`.

**Critical**: never import a component as a bare side-effect from a page-JS webpack bundle — `ol-components.js` already defines it site-wide; re-running `customElements.define()` throws `NotSupportedError: this name has already been used with this registry`.

### CSS conventions

**BEM** for templates and global styles (not required for Lit or Vue — they have built-in encapsulation):
```css
.book-card { }              /* Block */
.book-card__title { }       /* Element */
.book-card--featured { }    /* Modifier */
```

Rules:
- Explicit classes, not bare elements
- No IDs for styling
- Bottom margins only (never top) for vertical spacing
- Flat selectors; nesting only to win specificity wars with legacy CSS

### Shadow DOM vs Light DOM

| DOM type | Use for | Styling |
|----------|---------|---------|
| Shadow (default) | JS-instantiated widgets — dialogs, toasts, popovers | Lit `static styles` block |
| Light (`createRenderRoot() { return this }`) | Server-rendered page chrome, progressive enhancement | `static/css/components/<tag>.css` → registered in `ol-components.css` |

For Light DOM: style the tag itself for the pre-hydration phase and flip to component-rendered structure via a `hydrated` attribute — see `ol-button.css` / `OLButton.js`.

---

## Key Files

| File | Purpose |
|------|---------|
| `static/css/tokens/` | Two-tier design token files |
| `static/css/page-*.css` | Page-specific stylesheet bundles |
| `openlibrary/components/lit/` | Lit web component source |
| `openlibrary/components/lit/index.js` | Registration entry point — re-exports all components |
| `openlibrary/components/lit/custom-elements.json` | Generated manifest — source of API tables on /developers/design |
| `openlibrary/components/lit/utils/focus-utils.js` | `getDeepActiveElement()`, `findFocusableIndex()`, `isFocusable()` |
| `openlibrary/components/lit/utils/focusable-host-mixin.js` | `FocusableHostMixin` — fixes Shadow DOM focus discovery |
| `openlibrary/templates/site/footer.html` | Loads `ol-components.js` site-wide |
| `openlibrary/templates/design.html` | Component demo page |
| `custom-elements-manifest.config.mjs` | Manifest generator config |

---

## Configuration

**Bundle size limits** enforced in CI. Exceeding them:
```
FAIL static/build/page-plain.css: 18.81KB > maxSize 18.8KB (gzip)
```
Fix: remove unused styles, or move styles to a `<name>--js.css` (loaded via JS, higher threshold, off critical path).

**Browser support**: Firefox and Chromium-based browsers on desktop and mobile (iOS and Android).

---

## Testing

No dedicated frontend test suite documented in source. Component API tables are auto-generated from `custom-elements.json` (regenerated by manifest build). Playwright is the integration test layer — see [[development]] for the Playwright setup.

```bash
npm run build-assets:lit-manifest   # regenerate manifest
make lit-components                 # build components
```

---

## Accessibility (built into component standards)

Key rules from the Lit component standards:

- **Focus in Shadow DOM**: use `FocusableHostMixin` so outer focus traps can discover Shadow DOM components. `document.activeElement` returns the host, not the focused inner element — use `getDeepActiveElement()` from `focus-utils.js`.
- **ARIA on lists**: never put a non-list role directly on `<ul>` — it strips list semantics. Wrap in `<div role="radiogroup">` and keep `<ul>` pure.
- **Lit re-render focus loss**: stash focus target before `repeat` directive destroys a node; refocus in `updated()`. See `OlSelectPopover._onItemToggle` for the pattern.
- **Mobile autofocus**: don't autofocus a text input when opening a component on mobile — soft keyboard shrinks the panel. Gate: `if (!window.matchMedia('(max-width: 767px)').matches)`.
- **iOS Safari auto-zoom**: set `font-size: 16px` on every focusable text-entry control on mobile. Do NOT suppress auto-zoom with `maximum-scale=1` — that disables pinch-zoom (a11y failure).
- **Hover styles**: gate all `:hover` rules with `@media (hover: hover) and (pointer: fine)` — touch devices fire `:hover` on tap and the style sticks.

See [[i18n-rendering]] for translation patterns in Lit components.

---

## What's Broken / Fragile

- **Dual template engine**: Templetor (`.html`) is legacy but still heavily used. New work goes in Jinja (`.jinja`). A PR that edits a `.html` template should not convert it to Jinja unnecessarily — conversion is a separate concern.
- **`title_suggest` copy-field (Solr)**: mentioned in [[search]] — 3.4 GB unused. Unrelated but frontend queries don't cause this; it's a Solr schema concern.
- **httpx2 deprecation warning in OPDS tests**: harmless, suppress with `--disable-warnings` — see [[public-apis]].

---

## Tooling Gaps

- **No CLI path to attach real screenshots to a PR/issue comment.** `gh gist create` refuses binary files ("binary file not supported"), and there's no public `gh`/REST API for the `user-attachments` upload flow the web UI uses for drag-dropped images — that's a private, browser-only upload endpoint. When a PR process expects an attached screenshot, either accept a detailed textual description of what was verified (with exact repro steps so a human reviewer can regenerate the image), or ask a human to attach it manually. Don't try to reverse-engineer the private upload endpoint.

## Common Confusion

- **Vue is not the default**: Vue is reserved for specialized tools (librarian merge, reading stats). New interactive UI → Lit web component. Simple one-off enhancement → vanilla JS.
- **`customElements.define()` must run exactly once**: `ol-components.js` runs all defines site-wide. Never import a component module as a bare side-effect from a page-level webpack entry — it will re-define and throw.
- **BEM not required in Lit or Vue**: Lit has Shadow DOM encapsulation; Vue has `<style scoped>`. BEM is for global styles and templates.
- **Hover transitions belong on `:active`, not `:hover`**: hover background/color changes should be instant (no `transition`). A slow fade on `:hover` feels laggy. Transitions are for press feedback (`transform` on `:active`), enter/exit animations, and loading states.
- **`data-i18n` pattern for Lit components**: Lit can't use `$_()` — use the `data-i18n` bridge (server renders JSON into an attribute; JS reads it). See [[i18n-rendering]].

---

## Dependencies

**Depends on:**
- [[core-operations]] — Templetor/Jinja templates are served by the Infogami/web.py layer; webpack build produces assets that core-operations serves
- [[i18n-rendering]] — translation bridge pattern for Lit components

**Depended on by:**
- Every user-facing page

---

## Provisioning / Services

Static assets built via webpack, output to `static/build/`. Lit manifest generated separately. Both committed to the repo; no runtime build step.

---

*Sources: `raw/openlibrary-docs-ai/css.md`, `design.md`, `web-components.md` · See [[README]] · [[METHODOLOGY]]*
