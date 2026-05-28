# Web Component Standards

Guidelines for building Lit web components in Open Library. Components live in `openlibrary/components/lit/` and are registered in `openlibrary/components/lit/index.js`.

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
- Document with JSDoc: include `@element`, `@prop`, `@fires`, and `@example` tags. See `OlPagination.js` for the reference pattern.
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
- Trap focus inside modals.

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

## Styling

- Scope all styles via Lit's `static styles` (Shadow DOM).
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

Guard the `customElements.define()` call at the bottom of every component file:

```js
if (!customElements.get('ol-my-widget')) {
    customElements.define('ol-my-widget', OlMyWidget);
}
```

Some components get imported through both the central `lit-components` bundle and a downstream webpack consumer (e.g., the search-modal entrypoint). Without the guard, the second `define()` call throws `NotSupportedError: this name has already been used with this registry`, which surfaces as a blank page with no obvious cause.

If the component uses APIs that aren't available during SSR (e.g., `HTMLDialogElement`), also gate the `define()` call on `!isServer` from `lit`. See `OlDialog.js` for the pattern.

## Focus and Shadow DOM

Shadow DOM breaks the assumptions most focus-management code makes. The helpers in `openlibrary/components/lit/utils/focus-utils.js` and `FocusableHostMixin` exist to handle the cases below — reach for them rather than rolling your own.

### Make custom elements visible to outer focus traps

A custom element whose only focusable content is a `<button>` inside its shadow root is **invisible** to a focus trap that calls `querySelectorAll(FOCUSABLE_SELECTOR)` on light DOM. Two problems compound:

1. The trap's selector can't see into the shadow root, so the element is skipped entirely.
2. Calling `host.focus()` focuses the *host*, not the inner button — `:focus-visible` lands on nothing.

Apply `FocusableHostMixin` (`openlibrary/components/lit/utils/focusable-host-mixin.js`) to fix both at once. It sets `tabindex="0"` on the host (so traps discover it) and `delegatesFocus: true` on the shadow root (so `host.focus()` forwards to the first focusable inside and `:focus-visible` fires correctly). Override `_focusTarget` if the desired target isn't the first focusable in DOM order.

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
3. Add JSDoc to the class with `@element`, `@prop`, `@fires`, and `@example` tags (see `OlPagination.js` for the pattern).
4. Guard the `customElements.define()` call with `if (!customElements.get('ol-my-widget'))` — see [Registration](#registration).
5. Build with `npm run watch:lit-components` and verify the component renders at http://localhost:8080.
