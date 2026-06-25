# The shadow-boundary contract

Why some component behaviour needs deliberate work, when to use light vs shadow
DOM, and where each cross-boundary concern is handled. This is the umbrella; the
operational detail lives in [`web-components.md`](web-components.md) (building
components) and [`focus-tabbing.md`](focus-tabbing.md) (focus/Tab specifically).

## The one idea

The browser flattens the shadow tree for **two** things — sequential Tab order
and the accessibility *reading* tree — so basic tabbing and screen-reader
traversal "just work" across a shadow boundary. **Everything else that assumes a
single flat tree breaks at the boundary.** Four platform systems do, and a
component that wants a long life across light/shadow/nested usage has to have an
answer for each:

| System (assumes one flat tree) | What breaks at a shadow boundary | Our answer |
|---|---|---|
| **Sequential focus / Tab order** | `querySelectorAll`/`TreeWalker`/`activeElement` stop at the boundary; a focus trap can't see in, can't tell what's really focused | Shadow-piercing helpers + `FocusableHostMixin` — see [`focus-tabbing.md`](focus-tabbing.md) and `utils/focus-utils.js` |
| **CSS cascade** | Page CSS can't reach in; component CSS can't leak out (this is mostly the *point*) | Shadow by default + design tokens (which inherit through) + `::part`; light DOM only by the rule below |
| **Form participation** | A control rendered in shadow DOM submits **nothing** with the enclosing `<form>` | `FormAssociatedMixin` (`utils/form-associated-mixin.js`) — ElementInternals/FACE. See [web-components.md → Form participation](web-components.md#form-participation-formassociatedmixin) |
| **Cross-root ARIA (IDREFs)** | `aria-labelledby`/`-describedby`/`-controls`/`-activedescendant` and `<label for>` can't resolve an id in another root | Keep the relationship in one root; never claim `aria-modal` without a real trap+inert. See [ARIA across roots](#aria-across-roots) |

If you only remember one thing: **focus and reading order are free; styling,
forms, and id-based ARIA are not.**

## Light vs shadow: the decision rule

Default to **shadow DOM** (Lit's default). Reach for **light DOM**
(`createRenderRoot() { return this }`) deliberately, per component, only when one
of these holds:

- **Progressive enhancement / first-paint fidelity** — server-rendered page
  chrome that must look right before hydration (`ol-button`, `ol-banner`). Its
  CSS lives in `static/css/components/<tag>.css`, registered in
  `ol-components.css`.
- **Must live inside global page CSS** — a leaf that has to be styled by the
  surrounding stylesheet (e.g. a default trigger that reuses `ol-button.css`, as
  `ol-select-popover` injects).

Otherwise stay in shadow DOM: you keep style encapsulation, real `<slot>`
composition, and private internals, and you can't FOUC. Theme through tokens +
`::part`, never by expecting outside CSS to reach in. (This rule also lives,
operationally, in [web-components.md → Shadow DOM vs Light DOM](web-components.md#shadow-dom-vs-light-dom).)

## ARIA across roots

Element ids are scoped to their shadow root, so any **id-reference** ARIA
attribute silently fails to resolve across a boundary — in both directions. This
is the least-solved of the four systems today. Rules of thumb:

- **Keep an ARIA relationship within a single tree.** If a control and the thing
  it labels/controls/owns must reference each other, render them in the same
  root (or slot the related content into light DOM so it stays in the light
  tree). This is why a combobox/listbox is usually one component, not composed
  from separately-shadowed parts.
- **Don't claim `aria-modal="true"` unless it's true.** `aria-modal` tells AT
  the rest of the page is inert. Only set it on a surface that actually traps
  focus *and* inerts the background (native `<dialog>.showModal()` does both;
  see `ol-dialog`). A non-modal surface — a popover/menu/picker whose page stays
  interactive and that closes on outside-click — must **not** set it, and should
  let Tab leave (close-on-Tab-out) rather than trap. `ol-popover` is the
  reference: non-modal, no `aria-modal`, Tab off either edge closes it.
- **Prefer same-root or element-reflection over string ids.** Where a cross-root
  link is unavoidable, element-reference APIs (e.g. `ariaActiveDescendantElement`)
  beat string ids where supported.
- **Watch Reference Target** (`attachShadow({ referenceTarget })`, proposed for
  Interop 2026). It will let a shadow host stand in as the target of any
  attribute-based reference *while preserving encapsulation* — the real fix.
  Centralise id wiring (as `ol-popover` does with `_syncTriggerAria`) so adoption
  is a small, single-site change later.

## Status in this codebase

- **Focus/Tab** — handled; deep walker + `FocusableHostMixin` + roving helper.
  See [`focus-tabbing.md`](focus-tabbing.md).
- **CSS** — handled by Lit's `static styles` (shared `adoptedStyleSheets`) +
  tokens; light-DOM exceptions documented above.
- **Forms** — `ol-toggle`, `ol-segmented-control`, `ol-options-popover`,
  `ol-select-popover` are form-associated via `FormAssociatedMixin`.
- **Cross-root ARIA** — `aria-modal` corrected to truthful usage (`ol-dialog`
  modal; `ol-popover` non-modal). Remaining trigger→panel `aria-controls` links
  cross a boundary; acceptable in evergreen engines today, slated for Reference
  Target.
