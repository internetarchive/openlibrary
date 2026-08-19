# Web Component Standards

Guidelines for building Lit web components in Open Library. Components live in `openlibrary/components/lit/` and are registered in `openlibrary/components/lit/index.js`.

## The shadow-boundary contract

The browser flattens the shadow tree for exactly two things — sequential Tab order and the accessibility *reading* tree — so basic tabbing and screen-reader traversal cross a shadow boundary for free. **Every other platform system that assumes one flat tree breaks at the boundary.** Four do, and any component meant to live across light/shadow/nested usage needs an answer for each:

| System (assumes one flat tree) | What breaks at a shadow boundary | Our answer |
|---|---|---|
| **Sequential focus / Tab order** | `querySelectorAll`/`TreeWalker`/`activeElement` stop at the boundary; a focus trap can't see in or tell what's really focused | Shadow-piercing helpers + `FocusableHostMixin` — see [Focus and Shadow DOM](#focus-and-shadow-dom) |
| **CSS cascade** | Page CSS can't reach in; component CSS can't leak out (mostly the point) | Shadow by default + design tokens (they inherit through) + `::part`; light DOM only by the rule in [Shadow DOM vs Light DOM](#shadow-dom-vs-light-dom) |
| **Form participation** | A control rendered in shadow DOM submits **nothing** with the enclosing `<form>` | `FormAssociatedMixin` for value-carrying controls; the mixin plus a hidden light-DOM proxy `<button>` for submit buttons (`ol-button`) — see [Form participation](#form-participation-formassociatedmixin) |
| **Cross-root ARIA (IDREFs)** | `aria-labelledby`/`-describedby`/`-controls`/`-activedescendant` and `<label for>` can't resolve an id in another root | Keep the relationship in one root; never claim `aria-modal` without a real trap — see [ARIA across roots](#aria-across-roots) |

If you remember one thing: **focus and reading order are free; styling, forms, and id-based ARIA are not.**

## When to Build a Component

Not every interactive element needs a web component.

**Build a Lit web component when:**
- The UI is interactive and benefits from encapsulation (its own styles, state, events)
- The element will be reused across multiple pages or contexts
- The behavior is complex enough to warrant a clean API (attributes, events, slots)

**Use vanilla JavaScript when:**
- The interaction is a one-off page enhancement (e.g., toggling a section)
- The behavior is simple DOM manipulation tied to a specific template

**Use a template change when:**
- The change is purely visual or structural with no client-side interactivity

**Vue** is reserved for a few specialized, JavaScript-heavy tools (librarian merge UI, reading stats, library explorer). It is not the default for new UI.

Build and watch with:

```bash
npm run watch:lit-components   # Dev mode
make lit-components            # One-off build
```

## Naming

- **Tag names:** `ol-<name>` in kebab-case (e.g., `ol-pagination`, `ol-read-more`).
- **Class names:** PascalCase, prefixed with `Ol` (e.g., `OlPagination`). Legacy components may use `OL` (e.g., `OLReadMore`); prefer `Ol` for new work.
- **File names:** Match the class name (e.g., `OlPagination.js`).
- Register every new component in `openlibrary/components/lit/index.js`.

## API Design

- Start narrow — it is easy to add attributes later, hard to remove them.
- Attribute names: kebab-case, semantic (e.g., `total-pages`, not `tp`). Map to camelCase properties via `{ attribute: 'kebab-name' }`.
- Provide sensible defaults in the constructor.
- Document with JSDoc — it is the single source of truth for the auto-generated API tables on `/developers/design`. See [Documenting the API](#documenting-the-api-custom-elements-manifest) for the tags and `OlPagination.js` for the reference pattern.
- Boolean attributes: presence = true (no value needed).

### Compound Components

Use compound components when a component has multiple related parts that need to share state. Child elements use slots and the parent coordinates behavior.

```html
<!-- Good — compound components with slots -->
<ol-dialog>
  <button slot="trigger">Open</button>
  <div slot="content">
    <span slot="title">Are you sure?</span>
    <p slot="description">This action cannot be undone.</p>
    <button slot="close">Cancel</button>
  </div>
</ol-dialog>

<!-- Bad — prop drilling everything -->
<ol-dialog
  trigger="Open"
  title="Are you sure?"
  description="This action cannot be undone."
  close-text="Cancel"
></ol-dialog>
```

#### When to Use Compound Components

- Multiple related elements that share implicit state
- Components with slots (header, body, footer)
- Components where order/presence of children varies
- When you need flexible composition

#### When NOT to Use

- Simple components with fixed structure
- Components with 1-3 props
- When the structure never changes


## Documenting the API (Custom Elements Manifest)

The API reference tables on `/developers/design` are **generated, not hand-written**. JSDoc on each component is the source of truth: `@custom-elements-manifest/analyzer` reads it and emits `openlibrary/components/lit/custom-elements.json` (gitignored — a build artifact, regenerated by `make lit-components`), which `design.py` loads to render the tables. Tighten the JSDoc and the tables follow — there are no prop tables to maintain by hand.

To make a component's API appear in the tables:

- **Properties** — declare each public property in `static properties` and document it with `@prop {Type} name - description`. The *Attribute* column comes from the property's `attribute` mapping: use `{ attribute: 'kebab-name' }` for multi-word names; single-word props map 1:1.
- **Events** — `@fires event-name - description`. Describe the `detail` payload in the description (e.g. `detail: { selected: Boolean }`).
- **Slots** — `@slot - description` for the default slot; `@slot name - description` for named slots.
- **CSS custom properties** — `@cssprop [--name=default] - description`. The bracketed default fills the *Default* column.
- **CSS parts** — `@csspart name - description`.
- **Tag name** — read from `customElements.define('ol-name', ...)`. An explicit `@element ol-name` tag is optional, for clarity only.

Intentionally **excluded** from the tables: internal reactive state (Lit `state: true`, conventionally `_`-prefixed) and any non-public member — keep those out of `@prop`.

Example (from `OLChip.js`):

```js
/**
 * @prop {Boolean} selected - Whether the chip is in a selected state
 * @prop {String} accessibleLabel - Override aria-label on the inner element
 * @fires ol-chip-select - Fired on click. detail: { selected: Boolean }
 * @slot - The chip's label content
 */
export class OLChip extends LitElement {
  static properties = {
    selected: { type: Boolean, reflect: true },
    accessibleLabel: { type: String, attribute: 'accessible-label' },
  };
}
```

Regenerate the manifest after changing JSDoc so the local design page picks it up (the JSON is grep/AI-friendly and consumed at request time; it is not committed):

```bash
npm run build-assets:lit-manifest   # one-off — runs `npx cem analyze`
npm run watch:lit-manifest          # regenerate on change during dev
```

`make lit-components` also regenerates the manifest as part of the build. Config lives in `custom-elements-manifest.config.mjs`.

## HTML and Semantics

- Prefer semantic elements (`<nav>`, `<button>`, `<a>`) over generic `<div>` / `<span>`.
- Use `<slot>` for content projection when the component wraps user-provided markup.
- Provide accessible names via visible text, `aria-label`, or `aria-labelledby`.

## Accessibility

- Use ARIA roles appropriate to the widget pattern (e.g., `role="navigation"` on a pagination nav).
- Use `aria-live` regions for dynamic announcements.
- Use `aria-busy` during loading states.
- Use `aria-expanded`, `aria-selected`, `aria-current`, etc. to reflect interactive state.
- Support translatable labels via attribute overrides (see the `label-*` props on `OlPagination` for the pattern).

```js
// aria-live for dynamic content
html`
  <div aria-live="polite" aria-atomic="true">
    ${this.results.length} results found
  </div>
`;

// aria-expanded for toggleable sections
html`
  <button
    aria-expanded=${this.isOpen}
    aria-controls="panel"
    @click=${() => this.isOpen = !this.isOpen}
  >${this.heading}</button>
  <div id="panel" ?hidden=${!this.isOpen}>${this.content}</div>
`;

// aria-busy during loading
html`
  <div aria-busy=${this.loading}>
    ${this.loading
      ? html`<span>Loading...</span>`
      : html`<ul>${this.items.map(item => html`<li>${item}</li>`)}</ul>`}
  </div>
`;
```

## Keyboard

- Tab order must match visual order.
- Enter / Space activate buttons and actions.
- Arrow keys + Home / End for composite widgets (lists, pagination, tabs).
- Escape dismisses overlays and popups.
- Visible `:focus-visible` indicators on all interactive elements.
- Trap focus inside **modal** surfaces only (and inert the background + set
  `aria-modal` — native `<dialog>.showModal()` does all three, see `ol-dialog`).
  A **non-modal** popover/menu/picker must let Tab leave: close on Tab-out, don't
  trap, don't claim `aria-modal` (see `ol-popover`). Why this matters across
  shadow boundaries: [ARIA across roots](#aria-across-roots).

```js
// Escape to close — clean up listeners properly
connectedCallback() {
  super.connectedCallback();
  this._handleKeydown = (e) => {
    if (e.key === 'Escape' && this.open) {
      this.open = false;
    }
  };
  document.addEventListener('keydown', this._handleKeydown);
}

disconnectedCallback() {
  super.disconnectedCallback();
  document.removeEventListener('keydown', this._handleKeydown);
}
```

```css
/* Visible focus for keyboard users */
button:focus-visible {
  outline: 2px solid var(--focus-color);
  outline-offset: 2px;
}

/* Never remove focus outline without an alternative */
```

## Shadow DOM vs Light DOM

One facet of [the shadow-boundary contract](#the-shadow-boundary-contract). **Default to shadow DOM** (Lit's default). Reach for **light DOM** (`createRenderRoot() { return this }`) deliberately, per component, only when one of these holds:

- **Progressive enhancement / first-paint fidelity where layout is at stake** — server-rendered page chrome whose *size* must be right before hydration (`ol-banner`, currently the only one). Style the tag itself for the pre-hydration phase and flip to component-rendered structure via a `hydrated` attribute. Its CSS lives in `static/css/components/<tag>.css`, imported by `static/css/ol-components.css` (render-blocking, site-wide) — see `ol-banner.css` / `OlBanner.js` for the reference pattern.

Otherwise stay in shadow DOM: you keep style encapsulation, real `<slot>` composition, and private internals, and you can't FOUC. Theme through tokens + `::part`, never by expecting outside CSS to reach in.

A shadow-DOM component that is server-rendered can still look right before upgrade: put resting-state rules for the host tag in `static/css/components/<tag>.css`, keyed on `<tag>:not(:defined)`, and flush the first render synchronously in `connectedCallback` (`this.performUpdate()`) so there is no frame between the two. `ol-button` is the reference for this — it is composable inside other shadow roots *and* correct on first paint.

## Styling

- Shadow-DOM components: scope all styles via Lit's `static styles`.
- Light-DOM components: tag-scoped rules in `static/css/components/<tag>.css`, registered in `ol-components.css`.
- Use OL design tokens where possible. Token files live in `static/css/tokens/`.
- Avoid outer margins on reusable components — spacing between elements is the parent's responsibility.
- **Buttons inside a shadow root: compose `<ol-button>`, don't hand-copy its CSS.** `ol-button` renders in shadow DOM, so it works inside any other component's template (`ol-dialog` and `ol-toast` use it for their close controls). Add `import './OLButton.js';` at the top of the component so the element is registered whenever the component is — this is safe *within the Lit bundle* (ES modules evaluate once; the "never side-effect import from page JS" rule in [Registration](#registration) is about a second webpack bundle). Use `variant` / `size` / `shape` and the `icon-start` / `icon-end` slots for a leading or trailing SVG; only the glyph size (`.close-button svg { width … }`) belongs in the host component's styles. If the control genuinely isn't a button shape (pagination items, carousel arrows), keep a raw `<button>` and take the focus-ring / press-feedback rules from `ol-button` as the reference.

## Overlays and the top layer

Any panel that is **anchored to a trigger and positioned from viewport coordinates** — a popover, tooltip, menu, picker — must be promoted to the **top layer**. `position: fixed` is not enough and is the single most common way an overlay ships broken.

A fixed element's containing block is the viewport *only* if no ancestor establishes one. `transform`, `filter`, `perspective`, `backdrop-filter`, `contain` and `will-change` all do — including a bare `translateZ(0)` someone added for GPU compositing, and the transformed track inside a carousel. Under one of those, coordinates read from `getBoundingClientRect()` are resolved against the wrong origin and the panel lands far from its trigger, clipped by the container. Measured on the design-system docs inside a `translateZ(0)` wrapper: **`ol-popover` 441×364px off, `ol-tooltip` 436×367px off**. The top layer also escapes ancestor `isolation: isolate` and z-index stacking, which no z-index value can.

Use `utils/top-layer.js` rather than reaching for the Popover API directly:

```js
import { topLayerAttr, promoteToTopLayer, demoteFromTopLayer } from './utils/top-layer.js';

// In render() — emits nothing when the browser lacks support
html`<div class="panel" popover="${ifDefined(topLayerAttr())}">…</div>`;

// On show, BEFORE measuring; on hide, in your teardown path
promoteToTopLayer(panel);
demoteFromTopLayer(panel);
```

**Always `manual`, never `auto`.** `auto` brings light-dismiss and force-closes sibling popovers outside the ancestor chain, which silently collapses a component's own nesting and dismissal handling (`ol-popover` keeps an open-popover stack so Escape dismisses one layer at a time).

Two UA-stylesheet behaviours bite every time:

1. **`[popover]` is `display: none` until shown.** Promote *before* measuring or `offsetWidth`/`offsetHeight` read 0 and the collision math silently works from a zero-sized panel.
2. **The UA sets `inset: 0`, `margin: auto`, `width`/`height: fit-content`, `border`, `padding`, `overflow` and system colors on `[popover]`.** Author styles win by cascade origin — but *only for properties they actually declare*. Anything left undeclared inherits the UA value. Both bugs found this way were undeclared properties: `fit-content` beat `inset: 0` and collapsed `ol-popover`'s mobile backdrop to **0×0** (losing the dimming layer and its tap-to-dismiss target), and an undeclared `inset` on `.tooltip` would have combined with the inline `top` to stretch the tooltip to the viewport floor. Add an explicit `.panel[popover] { … }` reset next to the base rule, and place it *before* any variant rule (e.g. `.panel.tray`) that restates its own `inset`/`margin` — they carry equal specificity, so source order decides.

Browsers without the Popover API (Safari < 17, below [the Lit layer's floor](#focus-and-shadow-dom)) keep the plain `position: fixed` path, which is correct everywhere except under a containing-block ancestor. The detection is a module constant in `top-layer.js`; don't re-roll it.

**Pick the overlay mechanism by shape** — four are already correct, and new overlays should join one of them rather than invent a fifth:

| Overlay shape | Mechanism | Why it escapes the trap |
|---|---|---|
| Anchored to a trigger (`ol-popover`, `ol-tooltip`) | Popover API via `utils/top-layer.js` | Top layer; containing block is always the viewport |
| Modal (`ol-dialog`) | native `<dialog>.showModal()` | Promoted to the top layer by the browser — nothing to add |
| Viewport-fixed, unanchored (`ol-toast-region`, `OpenLibraryOTP`) | portal to `document.body` | No transformed ancestor exists on that path — **an invariant, not an accident**: mount these on `body`, never inside page content |
| Small panel anchored *inside* the component's own box (`OLMarkdownEditor`'s link/image/overflow menus) | in-flow `position: absolute` against a `position: relative` wrapper | Never reads viewport coordinates, so the containing-block trap cannot apply — but see the conditions below |

Composed components (`ol-menu-popover`, `ol-select-popover`, `ol-options-popover`) render through `ol-popover` and inherit the fix — don't add a second panel.

The fourth row is only safe while both conditions hold, and they are *not* enforced by anything:

1. **The panel fits inside the scroll container.** `OLMarkdownEditor` wraps everything in `.editor-wrapper { max-height: 70vh; overflow-y: auto }`, and `overflow-x: visible` computes to `auto` next to it — so the container clips on both axes. Vertically there is headroom by construction (`.editor-input` is `min-height: 200px`, the panels are ~40px). Horizontally there is not: the link panel is `min-width: 260px`, and measured on the real edit surfaces it clears the right edge by 256–502px, but a container narrower than **~470px** pushes it 20–40px past and raises a horizontal scrollbar. The demo on `/developers/design` sits at 478px and is already 2px over.
2. **The narrow-container mitigation actually fires.** It is a `@media (max-width: 767px)` rule that pins the panel `left`/`right` — keyed to the **viewport**, so a narrow editor inside a wide viewport gets nothing. A container query would be the honest fix if this ever needs one.

Prefer `ol-popover` for anything larger, anything that must escape its container, or anything on a new surface. `OLMarkdownEditor` deliberately does not use it: its toolbar `preventDefault()`s mousedown to keep the ProseMirror selection alive while you type a URL, and `ol-popover` moves focus into the panel and restores it on close, which would apply the link to the wrong range.

Components that call `getBoundingClientRect()` for *relative* measurement (`ol-segmented-control`'s pill offset, `OLReadMore`'s scroll check) are unaffected: a delta between two rects in the same coordinate space is transform-independent.

## Lifecycle and Performance

- Clean up listeners, observers, and timers in `disconnectedCallback`.
- Debounce expensive operations (resize handlers, scroll listeners, API calls).
- Use Lit's `state: true` for internal reactive properties that should not appear as attributes.

## Events

- Dispatch `CustomEvent` with an object `detail` payload.
- Event names: kebab-case, `ol-<component>-<action>` format (e.g., `ol-pagination-change`).
- Set `bubbles: true` and `composed: true` so events cross Shadow DOM boundaries.
- Document every emitted event in the class JSDoc with `@fires`.

## Slots

Named slots let consumers inject content without the component needing to know about it:

```js
render() {
  return html`
    <div class="card">
      <header><slot name="header"></slot></header>
      <div class="content"><slot></slot></div>
      <footer><slot name="footer"></slot></footer>
    </div>
  `;
}
```

```html
<ol-card>
  <h3 slot="header">Book Title</h3>
  <p>Description in the default slot.</p>
  <button slot="footer">Borrow</button>
</ol-card>
```

## Registration

Register the component once at the bottom of its file:

```js
customElements.define('ol-my-widget', OlMyWidget);
```

**`ol-components.js` is the single registration site for every `<ol-*>` custom element.** It is built from `openlibrary/components/lit/index.js` (which re-exports every component, running each `define()` as a side effect) and loaded site-wide from `openlibrary/templates/site/footer.html`.

If you need to drive a Lit component from page JS that webpack bundles (e.g., the search-modal entrypoint), import the component's exported class only if you need the class identifier — and never as a bare side-effect import. Re-running `customElements.define()` from a second bundle throws `NotSupportedError: this name has already been used with this registry`, which surfaces as a blank page with no obvious cause. The component will already be registered by `ol-components.js` before any page-JS handler (jQuery `DOMContentLoaded`) runs.

## Focus and Shadow DOM

Shadow DOM breaks the assumptions most focus-management code makes. The helpers in `openlibrary/components/lit/utils/focus-utils.js` and `FocusableHostMixin` exist to handle the cases below — reach for them rather than rolling your own.

> Browser floor for the Lit layer is **evergreen ~Safari 15.4+** (we rely on `delegatesFocus` and native `<dialog>.showModal()`); `package.json`'s browserslist still claims Safari 11.1, stale for this layer. The focus backbone is pure-JS and works below the floor; modern APIs are enhancement, never load-bearing.

Two hard problems sit under everything here:

1. **Discovery.** `querySelectorAll`/`TreeWalker`/`parentElement` stop at shadow boundaries, and `document.activeElement` only returns the outermost host. A focus trap must walk depth-first, pierce every `shadowRoot`, expand every `<slot>` via `assignedElements()`, and recurse `activeElement.shadowRoot.activeElement` to find what's really focused.
2. **Delegation.** `delegatesFocus: true` forwards `host.focus()` to the first focusable in the shadow root in DOM order. If that target is hidden it's a silent no-op; combine it with a host `tabindex` and you get two tab stops for one control. Both of our shipped focus bugs were one of these.

**Pick the focus pattern by the component's shape:**

| Component shape | Pattern | Host `tabindex` | `delegatesFocus` |
|---|---|---|---|
| Wraps **one** native focusable in its **own shadow** (`ol-button`, `ol-toggle`, `ol-chip`) | `FocusableHostMixin` | No | Yes |
| Focusable is a **slotted / light-DOM** child (`ol-select-popover`) | plain `LitElement`; the trigger *is* the focusable | No | No |
| **Composite** that owns its selection (`ol-segmented-control`) | roving tabindex (one `tabindex=0`, rest `-1`, arrows move) | per-item | No |
| **Navigation** list of links (`ol-pagination`) | every item is its own tab stop; arrows just move focus | natural | No |
| Renders into **light DOM** (`ol-banner`) | nothing special — naturally discoverable | n/a | n/a |

Rule of thumb: **delegate only when there is exactly one place focus can go.** If the component routes focus, or its focusable lives outside its own shadow, don't use `FocusableHostMixin`.

### The discovery backbone — `focus-utils.js`

`getTabbableElements(root)` / `getTabbableFromSlot(slot)` return tabbable elements in true DOM order, piercing shadow and expanding slots. The traps in `OlDialog` (keydown trap) and `OlPopover` (sentinel trap) build their focusable lists from these. Walker rules:

- A `<slot>` contributes its flattened assigned elements, in slot order.
- An element matching `FOCUSABLE_SELECTOR` **and not** `tabindex="-1"` is a tab stop. The explicit `-1` check matters: the selector matches native controls like `button` regardless of tabindex, and skipping `-1` is what keeps a roving composite to one stop.
- **Descent / leaf rule (mirrors native sequential focus):** a tab stop that has a `shadowRoot` is a self-contained widget → leaf, don't descend. Anything else is descended into, so a `role="button" tabindex="0"` row *and* its nested light-DOM button both count.
- Hidden/disabled subtrees (`isFocusable`, via `checkVisibility` with a fallback) are skipped. Closed shadow roots (`<video controls>`) are opaque.

Both arrow-navigation patterns (roving and multi-stop) share one tested helper, `getNextIndex()` in `utils/keyboard-nav.js` (Arrow/Home/End → destination index, with `orientation` + `wrap` + disabled-skipping). Roving vs. multi-stop is the *host's* choice (whether it renders `tabindex="-1"` on inactive items); the helper only computes where to move. Pagination is deliberately **not** roving — it's a `role="navigation"` list of links, and a single tab stop would stop users Tabbing directly to a page.

### Make custom elements visible to outer focus traps

A custom element whose only focusable content is a `<button>` inside its shadow root is **invisible** to a focus trap that calls `querySelectorAll(FOCUSABLE_SELECTOR)` on light DOM, and calling `host.focus()` focuses the *host*, not the inner button.

For a component wrapping **one** focusable in its own shadow root, apply `FocusableHostMixin` (`openlibrary/components/lit/utils/focusable-host-mixin.js`). It sets `delegatesFocus: true` on the shadow root — so `host.focus()` forwards to the first focusable inside and `:focus-visible` fires correctly on it. **It does not (and must not) set a host `tabindex`:** the inner native focusable is already in the tab order, and a host `tabindex` combined with `delegatesFocus` produces a double tab stop (host, then inner). Outer traps find the inner focusable through the shadow-piercing walker (`getTabbableElements` / `getTabbableFromSlot` in `focus-utils.js`), not via the host. Override `_focusTarget` if the desired target isn't the first focusable in DOM order.

```js
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';

export class OlMyWidget extends FocusableHostMixin(LitElement) {
    get _focusTarget() {
        return this.shadowRoot?.querySelector('.default-trigger');
    }
}
```

### Filter hidden elements from trap lists

Calling `.focus()` on a `display:none` or `visibility:hidden` element is a silent no-op. But `querySelectorAll(FOCUSABLE_SELECTOR)` still returns it, so the trap thinks focus moved when it didn't — Tab/Shift+Tab appear stuck on the previous element.

Use `el.checkVisibility({ visibilityProperty: true })` to filter (or `isFocusable()` from `focus-utils.js`, which wraps it). This bit us when a `display:none` close button in `SearchModal` kept jamming the dialog's focus trap.

### Walk shadow boundaries when reading active element

`document.activeElement` returns the *host*, not the deeply focused element inside a shadow root. When a trap needs to know "where is focus right now relative to my managed list?", use `getDeepActiveElement()` to drill in, then `findFocusableIndex()` to climb back out across shadow boundaries until it finds a host that the trap recognizes. Both are in `focus-utils.js`.

### Restore focus after Lit re-renders

When a `repeat` directive destroys a node — e.g., an item moves between two groups based on selected state, or a list re-sorts — the browser drops focus to `<body>`. Stash an identifying value, then refocus in `updated()` after the new node mounts:

```js
_onItemToggle(e) {
    // Only restore if the checkbox actually owned focus at toggle time
    if (this.shadowRoot?.activeElement === e.target) {
        this._restoreFocusToValue = e.target.value;
    }
    this._emitChange(/* ... */);
}

updated(changedProperties) {
    super.updated?.(changedProperties);
    if (this._restoreFocusToValue !== null && changedProperties.has('selected')) {
        const value = this._restoreFocusToValue;
        this._restoreFocusToValue = null;
        const target = this.shadowRoot?.querySelector(`[data-value="${value}"]`);
        target?.focus({ preventScroll: true });
    }
}
```

See `OlSelectPopover._onItemToggle` for the reference implementation.

### Testing focus

- jsdom **does** support `attachShadow`, slotting, and shadow `activeElement` traversal, so the walker and utilities are unit-tested faithfully (`tests/unit/js/focusUtils.test.js`).
- Real Lit components aren't instantiated in jest (tests use a `MockBase`), and jsdom has no `delegatesFocus`/`showModal`/layout. Verify full tab cycles deterministically: invoke the real handler (`{key:'Tab',shiftKey,preventDefault}`) and assert `getDeepActiveElement()`. **Always test Shift+Tab too** — reverse-only traps are invisible forward.

## Form participation (FormAssociatedMixin)

A control rendered in shadow DOM submits **nothing** with the enclosing `<form>`
by default — the form never sees its value. Make any control-shaped component a
form-associated custom element (FACE) with `FormAssociatedMixin`
(`utils/form-associated-mixin.js`), which wraps `ElementInternals`. Broadly
supported on our browser floor (Safari 16.4+).

The mixin provides `static formAssociated`, attaches internals, adds a reflected
`name`, delegates the standard form-control getters (`form`, `labels`,
`validity`, `checkValidity()`, …), and wires `formResetCallback` /
`formDisabledCallback`. The consumer supplies three things:

1. `get formValue()` — what to submit: a **string** (single value, under
   `name`), a **`FormData`** (multiple repeated entries, for a multi-select —
   you own the keys), a `File`, or `null` to contribute nothing.
2. A `this._syncFormValue()` call whenever that value changes — typically
   `firstUpdated()` (initial) + `updated()` (changes), or in the change handler.
3. Optionally `formReset()` — restore the default on `<form>.reset()` (capture
   the default once in `connectedCallback`).

```js
export class OlToggle extends FormAssociatedMixin(FocusableHostMixin(LitElement)) {
    get formValue() { return this.checked ? this.value : null; } // unchecked → nothing
    formReset() { this.checked = this._defaultChecked; }
    firstUpdated() { this._syncFormValue(); }
    updated(c) { if (c.has('checked') || c.has('value')) this._syncFormValue(); }
}
```

Reference implementations: `ol-toggle` (checkbox-shaped), `ol-segmented-control`
(radio group, always submits), `ol-options-popover` (single-select),
`ol-select-popover` (multi-select via `FormData`). Compose the mixin *outside*
`FocusableHostMixin` when both apply. See
[the shadow-boundary contract](#the-shadow-boundary-contract) for why this is one
of the four systems that breaks at a shadow boundary.

### Disabled: `isDisabled`, never mirror the callback

An ancestor `<fieldset disabled>` reaches the control through
`formDisabledCallback`. The mixin records it in `_formDisabled` and exposes
`isDisabled` (`disabled || _formDisabled`). **Gate interaction and render
`?disabled` from `isDisabled`, and style with `:host(:disabled)`** — the browser
keeps that pseudo-class in sync with both sources. Never write the callback's
value back into `disabled`: that reflects a `disabled` attribute onto the host,
and an attribute-disabled FACE stays disabled after the fieldset is re-enabled
(the browser sees no state change, so the callback never fires again). Verified
in `tests/e2e/ol-button-form.spec.ts`; jsdom has no fieldset plumbing.

### Submit buttons: a light-DOM proxy

`ElementInternals` gives a FACE a form owner but **not** submit-button
semantics: it can't be the form's default button (so Enter in a text field does
nothing once the form has two text fields), can't be `SubmitEvent.submitter`,
and contributes no `name`/`value`. `ol-button` closes that gap by keeping a
hidden native `<button type="submit|reset">` in its **light DOM** — given a slot
name that doesn't exist, so it never renders — mirroring `type`, `name`,
`value`, `disabled`/`loading`, and the `form*` attributes. Being a real submit
button in the form's tree, it is the default button, and a click on the visible
control is forwarded as `form.requestSubmit(proxy)`, **deferred with
`setTimeout(0)`** so `preventDefault()` on the host or an ancestor cancels the
submission the way it does for a native button (a microtask is too early — for
user input the browser drains microtasks between listeners). When the button is
inside another component's shadow root and the form outside, the proxy has no
form owner and it falls back to `internals.form.requestSubmit()`. Same shape as
Lion's `lion-button` and FAST's button proxy.

## ARIA across roots

Element ids are scoped to their shadow root, so any **id-reference** ARIA attribute silently fails to resolve across a boundary, in both directions. This is the least-solved of the four boundary systems today.

- **Keep an ARIA relationship within a single tree.** If a control and the thing it labels/controls/owns must reference each other, render them in the same root (or slot the related content into light DOM so it stays in the light tree). This is why a combobox/listbox is usually one component, not composed from separately-shadowed parts.
- **Don't claim `aria-modal="true"` unless it's true.** It tells assistive tech the rest of the page is inert. Set it only on a surface that actually traps focus *and* inerts the background (native `<dialog>.showModal()` does both — see `ol-dialog`). A non-modal popover/menu/picker whose page stays interactive must **not** set it, and should let Tab leave (close-on-Tab-out) rather than trap — `ol-popover` is the reference.
- **Prefer same-root or element-reflection over string ids.** Where a cross-root link is unavoidable, element-reference APIs (e.g. `ariaActiveDescendantElement`) beat string ids where supported. The `attachShadow({ referenceTarget })` proposal (Interop 2026) is the real fix; centralise id wiring (as `ol-popover` does in `_syncTriggerAria`) so adoption is a single-site change later.

## ARIA on lists

Putting a non-list role like `role="radiogroup"` directly on a `<ul>` **strips the list semantics**. The `<li>` children then become invalid in the accessibility tree (a `<li>` is only valid inside `<ul>`, `<ol>`, or `<menu>`), and accesslint will flag it.

Separate the roles: wrap the list in a `<div role="radiogroup">` and keep the `<ul>` pure.

```js
// Bad — strips list semantics
html`<ul role="radiogroup" aria-label=${label}>
       ${items.map(item => html`<li>...</li>`)}
     </ul>`;

// Good — separate roles
html`<div role="radiogroup" aria-label=${label}>
       <ul>${items.map(item => html`<li>...</li>`)}</ul>
     </div>`;
```

Related: whitespace inside `<ul>` template literals creates real text nodes that accesslint flags as direct text content inside a list. Keep `<li>` flush against the opening `<ul>` tag — no leading newline.

## Autofocus on mobile

Don't auto-focus a text input when a component opens on a mobile breakpoint — the soft keyboard pops up and shrinks the visible panel area to nothing. Gate the focus call:

```js
_onPopoverOpen() {
    if (!window.matchMedia('(max-width: 767px)').matches) {
        this.shadowRoot.querySelector('.filter-input')?.focus();
    }
}
```

767px matches the breakpoint that `ol-popover` uses to switch into its mobile tray layout — stay consistent with that so behavior matches what the user sees.

(Inputs in this component should also use `font-size: 16px` to prevent iOS Safari's auto-zoom on focus — see [design.md](design.md#mobile).)

## New Component Checklist

1. Create a file in `openlibrary/components/lit/` named after the class (e.g., `OlMyWidget.js`).
2. Register the component by adding an export to `openlibrary/components/lit/index.js`.
3. Add JSDoc to the class documenting the public API — `@prop`, `@fires`, `@slot`, `@cssprop`, `@csspart` (see [Documenting the API](#documenting-the-api-custom-elements-manifest)). This drives the generated API tables; no hand-written prop tables.
4. Regenerate the Custom Elements Manifest (`npm run build-assets:lit-manifest`) so the API table renders locally; the JSON is gitignored and rebuilt by `make lit-components` in CI/deploy.
5. Add a demo partial at `openlibrary/templates/design/components/<id>.html.jinja` defining a `{% macro demos() %}` of `ex.example(...)` calls, and register a `Component(...)` row in `COMPONENTS` in `openlibrary/plugins/openlibrary/design.py`. The row drives the sidebar, section order, and the *Use when* / *Avoid* lines; the API table renders from the manifest. Nothing on the page is hand-listed — `openlibrary/templates/design.html` is only a shim into `design/layout.html.jinja`, so there is no section markup to add there.
6. If it renders an anchored overlay panel, promote it to the top layer — see [Overlays and the top layer](#overlays-and-the-top-layer).
7. Build with `npm run watch:lit-components` and verify the component renders at http://localhost:8080/developers/design.
