# Web Component Standards

Guidelines for building Lit web components in Open Library. Components live in `openlibrary/components/lit/` and are registered in `openlibrary/components/lit/index.js`.

## The shadow-boundary contract

The browser flattens the shadow tree for exactly two things — sequential Tab order and the accessibility *reading* tree — so basic tabbing and screen-reader traversal cross a shadow boundary for free. **Every other platform system that assumes one flat tree breaks at the boundary.** Four do, and any component meant to live across light/shadow/nested usage needs an answer for each:

| System (assumes one flat tree) | What breaks at a shadow boundary | Our answer |
|---|---|---|
| **Sequential focus / Tab order** | `querySelectorAll`/`TreeWalker`/`activeElement` stop at the boundary; a focus trap can't see in or tell what's really focused | Shadow-piercing helpers + `FocusableHostMixin` — see [Focus and Shadow DOM](#focus-and-shadow-dom) |
| **CSS cascade** | Page CSS can't reach in; component CSS can't leak out (mostly the point) | Shadow by default + design tokens (they inherit through) + `::part`; light DOM only by the rule in [Shadow DOM vs Light DOM](#shadow-dom-vs-light-dom) |
| **Form participation** | A control rendered in shadow DOM submits **nothing** with the enclosing `<form>` | `FormAssociatedMixin` — see [Form participation](#form-participation-formassociatedmixin) |
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

The API reference tables on `/developers/design` are **generated, not hand-written**. JSDoc on each component is the source of truth: `@custom-elements-manifest/analyzer` reads it and emits `openlibrary/components/lit/custom-elements.json` (committed to the repo), which `design.py` loads to render the tables. Tighten the JSDoc and the tables follow — there are no prop tables to maintain by hand.

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

Regenerate the manifest after changing JSDoc and **commit the result** (the JSON is grep/AI-friendly and consumed at request time):

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

- **Progressive enhancement / first-paint fidelity** — server-rendered page chrome that must look right before hydration (`ol-button`, `ol-banner`). Style the tag itself for the pre-hydration phase and flip to component-rendered structure via a `hydrated` attribute. Its CSS lives in `static/css/components/<tag>.css`, imported by `static/css/ol-components.css` (render-blocking, site-wide) — see `ol-button.css` / `OLButton.js` for the reference pattern.
- **Must live inside global page CSS** — a leaf that has to be styled by the surrounding stylesheet (e.g. a default trigger that reuses `ol-button.css`, as `ol-select-popover` injects).

Otherwise stay in shadow DOM: you keep style encapsulation, real `<slot>` composition, and private internals, and you can't FOUC. Theme through tokens + `::part`, never by expecting outside CSS to reach in.

## Styling

- Shadow-DOM components: scope all styles via Lit's `static styles`.
- Light-DOM components: tag-scoped rules in `static/css/components/<tag>.css`, registered in `ol-components.css`.
- Use OL design tokens where possible. Token files live in `static/css/tokens/`.
- Avoid outer margins on reusable components — spacing between elements is the parent's responsibility.

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
| Wraps **one** native focusable in its **own shadow** (`ol-toggle`, `ol-chip`) | `FocusableHostMixin` | No | Yes |
| Focusable is a **slotted / light-DOM** child (`ol-select-popover`) | plain `LitElement`; the trigger *is* the focusable | No | No |
| **Composite** that owns its selection (`ol-segmented-control`) | roving tabindex (one `tabindex=0`, rest `-1`, arrows move) | per-item | No |
| **Navigation** list of links (`ol-pagination`) | every item is its own tab stop; arrows just move focus | natural | No |
| Renders its control into **light DOM** (`ol-button`) | nothing special — naturally discoverable | n/a | n/a |

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
4. Regenerate the Custom Elements Manifest (`npm run build-assets:lit-manifest`) and commit the updated `openlibrary/components/lit/custom-elements.json`.
5. Add a demo `<section>` for the component to `openlibrary/templates/design.html` — the API tables render automatically from the manifest.
6. Build with `npm run watch:lit-components` and verify the component renders at http://localhost:8080/developers/design.
