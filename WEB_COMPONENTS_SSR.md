# Web Components Server-Side Rendering (SSR)

## The Problem

Open Library uses [Lit web components](https://lit.dev/) — custom HTML elements like `<ol-read-more>` and `<ol-pagination>` that handle their own rendering and interactivity. The catch is that these components are **JavaScript-powered**. Until the browser downloads, parses, and executes the JavaScript bundle, the components are empty shells. Users see either:

- **Nothing** — a blank gap where the component should be
- **A flash of unstyled content (FOUC)** — raw content that suddenly snaps into place when JS loads
- **Layout shift** — the page jumps around as components pop into existence

This is especially bad on slow connections, older devices, or when JavaScript fails to load entirely.

## The Solution: Declarative Shadow DOM (DSD)

We solve this by **pre-rendering** each component's visual output directly into the HTML that the server sends to the browser. The browser can display the component's styles and structure **instantly** — no JavaScript needed for the first render.

The key browser feature that makes this work is called [Declarative Shadow DOM](https://developer.chrome.com/docs/css-ui/declarative-shadow-dom). Here's what it looks like in practice.

### Before (client-side only)

The server sends an empty custom element. Nothing shows until JS loads.

```html
<ol-read-more max-height="80px" more-text="Read More" less-text="Read Less">
  <p>A long book description that should be truncated...</p>
</ol-read-more>
```

The browser sees `<ol-read-more>` but doesn't know what to do with it. It waits for JavaScript to define the element and render its shadow DOM (internal HTML, styles, buttons, etc).

### After (with SSR)

The server sends the component **with its shadow DOM already filled in**:

```html
<ol-read-more max-height="80px" more-text="Read More" less-text="Read Less">
  <template shadowrootmode="open">
    <style>
      :host { display: block; position: relative; }
      .content-wrapper { overflow: hidden; }
      .toggle-btn { /* ... button styles ... */ }
    </style>
    <!--lit-part ...-->
    <div class="content-wrapper" style="max-height: 80px">
      <slot></slot>
    </div>
    <button class="toggle-btn more" aria-expanded="false">
      Read More <svg><!-- chevron icon --></svg>
    </button>
    <button class="toggle-btn less hidden" aria-expanded="true">
      Read Less <svg><!-- chevron icon --></svg>
    </button>
    <!--/lit-part-->
  </template>
  <p>A long book description that should be truncated...</p>
</ol-read-more>
```

Two things to notice:

1. **`<template shadowrootmode="open">`** — When the browser's HTML parser encounters this tag, it **immediately** creates a shadow root and attaches the styles and HTML inside it. No JavaScript needed. The component looks correct from the very first frame of rendering.

2. **`<!--lit-part-->`** — These HTML comments are template markers from Lit's SSR package. They tell Lit exactly where its template bindings are, so it can **hydrate** (reuse the existing DOM) instead of tearing it down and re-rendering from scratch.

### What happens when JavaScript finally loads

1. Lit sees the `<ol-read-more>` element and initializes its component class
2. It finds the existing shadow root and recognizes the `<!--lit-part-->` markers
3. It **hydrates** — walks the existing DOM nodes and attaches event listeners to them
4. No re-render, no flash, no layout shift
5. The "Read More" / "Read Less" buttons become clickable

The user sees styled content immediately. It becomes interactive once JS loads.

---

## How It Works in Open Library

This uses the [official Lit SSR approach](https://lit.dev/docs/ssr/overview/) via the `@lit-labs/ssr` package. The system has four parts.

### Part 1: The Node.js SSR Server

**File:** `openlibrary/components/lit/ssr/server.mjs`

A long-running Node.js process that:

1. Imports the actual Lit component source files (`OLReadMore.js`, `OlPagination.js`)
2. Uses `@lit-labs/ssr` to render them using their real `render()` methods
3. Communicates with Python over stdin/stdout using line-delimited JSON

The important thing: **the components render themselves**. We don't write any HTML generation code. `@lit-labs/ssr` calls the same `render()` method that the browser calls, producing identical output — plus the Lit template markers needed for hydration.

**Protocol:**

```
Python sends:  {"tag": "ol-read-more", "attrs": {"max-height": "80px"}, "content": "<p>...</p>"}
Node responds: {"html": "<ol-read-more ...><template shadowrootmode=\"open\">...</template><p>...</p></ol-read-more>"}
```

The server starts lazily on the first render request and stays running for the lifetime of the Python process. Startup is ~65ms; each subsequent render is <1ms.

### Part 2: The Python Helpers

**File:** `openlibrary/core/dsd.py`

This module provides template-callable functions that send render requests to the Node.js server and return the HTML:

- **`dsd_read_more()`** — Returns the opening `<ol-read-more>` tag with its DSD. You put your slot content after it and close with `dsd_read_more_close()`.
- **`dsd_pagination()`** — Returns a complete `<ol-pagination>` element with its DSD.

If Node.js is unavailable (e.g. in a test environment), these fall back to plain custom elements without DSD. The page still works — components just render client-side like they did before.

These functions are registered as **template globals** in `openlibrary/plugins/openlibrary/code.py`, so any Templetor template can call them with `$:`.

### Part 3: Client-Side Hydration

**File:** `openlibrary/components/lit/index.js`

The Lit bundle imports `@lit-labs/ssr-client/lit-element-hydrate-support.js` **before** any component imports:

```js
// Must come before any component imports
import '@lit-labs/ssr-client/lit-element-hydrate-support.js';

import { OLReadMore } from './OLReadMore.js';
import { OlPagination } from './OlPagination.js';
```

This import order matters. The hydration support module patches `LitElement` so that when a component initializes, it checks: "Do I already have a shadow root with Lit template markers?" If yes, it hydrates (reuses the DOM, attaches event listeners). If no (e.g. a component added dynamically via JavaScript), it renders normally.

Components don't need to know whether they were server-rendered. Both paths work.

### Part 4: The Browser Fallback

**File:** `openlibrary/templates/site/head.html`

Most modern browsers (Chrome 111+, Edge 111+, Safari 16.4+, Firefox 123+) support Declarative Shadow DOM natively. For older browsers, we include two things in the `<head>`:

1. **A CSS rule** that hides undefined components only in browsers that don't support DSD:

   ```css
   @supports not (selector(:has(> template[shadowrootmode]))) {
     ol-read-more:not(:defined),
     ol-pagination:not(:defined) {
       visibility: hidden;
     }
   }
   ```

2. **A polyfill script** that finds `<template shadowrootmode>` elements and manually converts them into shadow roots. It runs synchronously in the `<head>` so there's no flash.

---

## Using DSD in Templates

### For `ol-read-more`

This component uses a "slot" to wrap content, so the DSD call is split into an open and close:

```html
$# Before:
<ol-read-more more-text="$_('Read More')" less-text="$_('Read Less')">
  <p>Content here...</p>
</ol-read-more>

$# After:
$:dsd_read_more(more_text=_('Read More'), less_text=_('Read Less'))
  <p>Content here...</p>
$:dsd_read_more_close()
```

The `$:` prefix in Templetor means "output this as raw HTML" (don't escape it).

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_height` | `"80px"` | CSS max-height for the collapsed state |
| `more_text` | `"Read More"` | Text for the expand button |
| `less_text` | `"Read Less"` | Text for the collapse button |
| `label_size` | `"medium"` | Button text size: `"medium"` or `"small"` |
| `background_color` | `None` | Background color for the gradient fade |
| `**attrs` | — | Any extra HTML attributes (e.g., `class`) |

To pass HTML attributes like `class`, use `**kwargs`:

```html
$:dsd_read_more(more_text=_('Show more'), **{'class': 'srw__chapters'})
```

### For `ol-pagination`

Pagination has no slot content, so it's a single call:

```html
$# Before:
<ol-pagination total-pages="$total" current-page="$page" base-url="/search?q=$q"></ol-pagination>

$# After:
$:dsd_pagination(current_page=page, total_pages=total, base_url='/search?q=' + q)
```

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `current_page` | `1` | Currently selected page (1-indexed) |
| `total_pages` | `1` | Total number of pages |
| `base_url` | `""` | Base URL for page links (omit for event-only mode) |
| `label_previous_page` | `"Go to previous page"` | Aria label for previous button |
| `label_next_page` | `"Go to next page"` | Aria label for next button |
| `label_go_to_page` | `"Go to page {page}"` | Aria label template for page buttons |
| `label_current_page` | `"Page {page}, current page"` | Aria label for current page |
| `label_pagination` | `"Pagination"` | Aria label for the nav landmark |

---

## Adding SSR for a New Component

Because this uses `@lit-labs/ssr` with the real component code, **you don't write any HTML rendering logic**. The component renders itself. Here's what you do:

### Step 1: Import the component in the SSR server

Open `openlibrary/components/lit/ssr/server.mjs` and add an import:

```js
import '../OLReadMore.js';
import '../OlPagination.js';
import '../OlYourComponent.js';  // Add this
```

This is the only step that touches the Node.js side. The `@lit-labs/ssr` package will now be able to render your component.

### Step 2: Add a Python wrapper function

Open `openlibrary/core/dsd.py` and add a function that maps Python keyword arguments to HTML attributes. This is a thin translation layer — it doesn't generate any HTML itself:

```python
def dsd_your_component(some_prop: str = 'default', **attrs: str) -> str:
    component_attrs = {'some-prop': some_prop}
    all_attrs = _build_attrs(component_attrs, attrs)
    ssr_html = _ssr_render('ol-your-component', all_attrs)
    if ssr_html:
        return ssr_html
    # Fallback: plain element for client-side rendering
    attr_str = ' '.join(f'{k}="{escape(v)}"' for k, v in all_attrs.items())
    return f'<ol-your-component {attr_str}></ol-your-component>'
```

If your component uses slots (like `ol-read-more`), you'll also need a `dsd_your_component_close()` function and the same `</template>` splitting logic — look at `dsd_read_more()` for the pattern.

### Step 3: Register as a template global

In `openlibrary/plugins/openlibrary/code.py`, inside `setup_template_globals()`:

```python
from openlibrary.core.dsd import dsd_your_component

web.template.Template.globals.update({
    # ...existing globals...
    'dsd_your_component': dsd_your_component,
})
```

### Step 4: Add fallback CSS for older browsers

In `openlibrary/templates/site/head.html`, add your tag to the `@supports` block:

```css
ol-read-more:not(:defined),
ol-pagination:not(:defined),
ol-your-component:not(:defined) {
  visibility: hidden;
}
```

### Step 5: Test

```bash
python -m pytest openlibrary/tests/core/test_dsd.py --noconftest -v
npx jest
pre-commit run --all-files
```

### What you DON'T have to do

- Write any HTML generation code
- Replicate the component's `render()` method in Python
- Keep Python rendering logic in sync when the component changes
- Add build steps

If you change a component's `render()` method or styles, the SSR output updates automatically because `@lit-labs/ssr` runs the real code.

---

## Designing Components for SSR

Lit components work with SSR out of the box if they follow standard Lit patterns. The rules:

1. **Use shadow DOM** — Render into the shadow root, which is LitElement's default. Don't override `createRenderRoot()` to return `this`.

2. **No browser APIs in `constructor()` or `render()`** — Things like `window`, `document`, `localStorage`, `navigator`, `fetch`, etc. don't exist on the server. Use them in lifecycle methods that only run in the browser: `connectedCallback()`, `firstUpdated()`, `updated()`, or event handlers.

3. **Keep `render()` pure** — It should be a function of the component's properties. No side effects, no DOM queries, no async operations. This is already a Lit best practice.

4. **Use `<slot>` for content projection** — Rather than reading `innerHTML` or `textContent`, use `<slot></slot>` to let the parent pass content through.

If your component follows these patterns (which it should anyway), SSR works with zero changes to the component code.

---

## File Reference

| File | Role |
|------|------|
| `openlibrary/components/lit/ssr/server.mjs` | Persistent Node.js SSR server (stdin/stdout JSON protocol) |
| `openlibrary/components/lit/ssr/render.mjs` | Standalone CLI for one-off SSR renders (useful for debugging) |
| `openlibrary/core/dsd.py` | Python helpers that templates call; manages the Node.js subprocess |
| `openlibrary/components/lit/index.js` | Client bundle entry; imports hydration support before components |
| `openlibrary/templates/site/head.html` | DSD polyfill and fallback CSS for older browsers |
| `openlibrary/plugins/openlibrary/code.py` | Registers DSD helpers as Templetor template globals |
| `openlibrary/tests/core/test_dsd.py` | Python tests for the DSD helpers |

**npm dependencies** (in `package.json` devDependencies):

| Package | Role |
|---------|------|
| `@lit-labs/ssr` | Official Lit SSR renderer — runs component `render()` in Node.js |
| `@lit-labs/ssr-client` | Client-side hydration support — teaches Lit to reuse server-rendered DOM |

---

## Architecture Diagram

```
Browser Request
      |
      v
Python Server (Infogami/FastAPI)
      |
      |  Template calls dsd_read_more() or dsd_pagination()
      v
openlibrary/core/dsd.py
      |
      |  JSON over stdin: {"tag": "ol-read-more", "attrs": {...}, "content": "..."}
      v
Node.js SSR Server (ssr/server.mjs)
      |
      |  @lit-labs/ssr calls the component's real render() method
      |  Output includes styles, HTML, and <!--lit-part--> markers
      v
JSON over stdout: {"html": "..."}
      |
      v
Python injects HTML into page response
      |
      v
Browser receives full HTML
      |
      |
      ├─→ HTML parser encounters <template shadowrootmode="open">
      |   → Creates shadow root immediately (no JS needed)
      |   → Styles apply, layout is correct, content is visible
      |
      └─→ Later: Lit JS bundle loads
          → Finds existing shadow root with <!--lit-part--> markers
          → Hydrates: walks DOM, attaches event listeners
          → Component is now interactive (no re-render)
```

---

## Debugging

### See what the SSR server produces

Use the standalone `render.mjs` CLI to render a component and inspect the output:

```bash
node openlibrary/components/lit/ssr/render.mjs \
  '<ol-pagination total-pages="10" current-page="3"></ol-pagination>'
```

### Verify SSR is working on a page

View the HTML source of a page (Ctrl+U / Cmd+U, not the DevTools Elements panel). Look for `<template shadowrootmode="open">` inside your custom element tags. If it's there, SSR is working.

### Check if hydration is working

In DevTools, look at the console when the page loads. If hydration fails, Lit logs a warning and falls back to a full re-render. No warnings = hydration succeeded.

### SSR server won't start

Check that Node.js is installed and accessible. The Python helper logs a warning if it can't start the server:

```
SSR server failed to start (no output)
Node.js not found — SSR disabled, components will render client-side
```

The page still works — components just render client-side.

---

## FAQ

**Q: Is this the official Lit SSR approach?**

Yes. We use [`@lit-labs/ssr`](https://lit.dev/docs/ssr/server-usage/) (the official server-rendering package) and [`@lit-labs/ssr-client`](https://lit.dev/docs/ssr/client-usage/) (the official hydration support). Components render themselves using their real `render()` methods — no hand-written HTML replication.

**Q: Do I have to write custom rendering code for each new component?**

No. You add one `import` line to `server.mjs` and a thin Python wrapper (~10 lines) that translates keyword arguments to HTML attributes. The wrapper doesn't generate HTML — it sends a request to Node and returns whatever comes back.

**Q: Do components need to be designed differently for SSR?**

No, as long as they follow standard Lit patterns. The only thing to avoid: don't use browser-only APIs (`window`, `document`, etc.) in `constructor()` or `render()`. Use them in `connectedCallback`, `firstUpdated`, `updated`, or event handlers instead.

**Q: What if Node.js isn't available?**

The Python helpers fall back to plain custom elements without DSD. Components render client-side as they did before SSR. No errors, no broken pages.

**Q: Does this add latency to page renders?**

The Node.js process starts once (~65ms) on the first SSR call. After that, each render is <1ms over stdin/stdout. The process stays alive for the lifetime of the Python server, so there's no repeated startup cost.

**Q: What about browsers that don't support Declarative Shadow DOM?**

A polyfill in the `<head>` handles them. It runs before the page renders, converting `<template shadowrootmode>` tags into real shadow roots. A CSS `@supports` rule hides components only in browsers that need the polyfill.

**Q: How do I verify SSR is working?**

View the page source (Ctrl+U). You should see `<template shadowrootmode="open">` inside your custom elements with styles and HTML structure inside them. If you only see empty custom element tags, SSR isn't running for those elements.
