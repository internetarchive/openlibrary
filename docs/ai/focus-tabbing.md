# Focus & tabbing in Lit web components

How keyboard focus and Tab order work across our Lit components, the rules to
follow when building a focusable component, and the phased plan to harden it.

> Browser floor for the Lit layer is **evergreen ~Safari 15.4+** (we rely on
> `delegatesFocus` and native `<dialog>.showModal()`). `package.json`'s
> browserslist still claims Safari 11.1 — that's stale for this layer. The focus
> backbone is nonetheless pure-JS (works below the floor too); modern APIs are
> enhancement, never load-bearing for correctness.

## The two hard problems

1. **Discovery.** `querySelectorAll`/`TreeWalker`/`parentElement` stop at shadow
   boundaries, and `document.activeElement` only returns the outermost host. A
   JS focus trap must walk depth-first, pierce every `shadowRoot`, expand every
   `<slot>` via `assignedElements()`, and recurse `activeElement.shadowRoot.
   activeElement` to find what's really focused.
2. **Delegation.** `delegatesFocus: true` forwards `host.focus()` to the *first
   focusable in the shadow root, in DOM order*. If that target is hidden it's a
   silent no-op; combine it with a host `tabindex` and you get two tab stops for
   one control. Both of our shipped focus bugs were one of these.

## Decision table — building a focusable component

| Shape | Pattern | Host `tabindex`? | `delegatesFocus`? |
|---|---|---|---|
| Wraps **one** native focusable in its **own shadow** (`ol-toggle`, `ol-chip`) | `FocusableHostMixin` | No | Yes |
| Wrapper whose focusable is a **slotted / light-DOM** child (`ol-select-popover`) | Plain `LitElement`; the trigger *is* the focusable | No | No |
| **Composite** with many focusables (`ol-segmented-control`, `ol-pagination`) | Roving tabindex (one `tabindex=0`, rest `-1`, arrows move) | per-item | No |
| Renders its control into **light DOM** (`ol-button`) | Nothing special — naturally discoverable | n/a | n/a |

The mixin sets `delegatesFocus` only — **never** a host `tabindex` (that would
double-stop). The inner native focusable is tabbable on its own, and the traps
find it via the deep walker.

Rule of thumb: **delegate only when there is exactly one place focus can go.**
If the component routes focus, or its focusable lives outside its own shadow,
don't use `FocusableHostMixin`.

## The discovery backbone — `focus-utils.js`

`getTabbableElements(root)` / `getTabbableFromSlot(slot)` return tabbable
elements in true DOM order, piercing shadow and expanding slots. Walker rules:

- A `<slot>` contributes its flattened assigned elements, in slot order.
- An element matching `FOCUSABLE_SELECTOR` **and not** `tabindex="-1"` is a tab
  stop (the explicit `-1` check is needed because the selector matches native
  controls like `button` regardless of tabindex — this is what keeps a roving
  composite to one stop).
- **Descent / leaf rule (mirrors native sequential focus):** a tab stop that
  has a `shadowRoot` is a self-contained widget → leaf, don't descend. Anything
  else is descended into — so a `role="button" tabindex="0"` row *and* its
  nested light-DOM button both count.
- Hidden/disabled subtrees (`isFocusable`, via `checkVisibility` with a
  fallback) are skipped. Closed shadow roots (`<video controls>`) are opaque.

The traps in `OlDialog` (`_handleKeyDown` keydown trap) and `OlPopover`
(sentinel trap) build their focusable lists from these helpers.

## Testing

- jsdom **does** support `attachShadow`, slotting, and shadow `activeElement`
  traversal — so the walker + utilities are unit-tested faithfully
  (`tests/unit/js/focusUtils.test.js`).
- Real Lit components aren't instantiated in jest (tests use a `MockBase`), and
  jsdom has no `delegatesFocus`/`showModal`/layout. Full tab-cycle verification
  is deterministic-in-browser: invoke the real handler (`{key:'Tab',shiftKey,
  preventDefault}`) and assert `getDeepActiveElement()`. **Always test Shift+Tab
  too** — reverse-only traps are invisible forward.

## Phased plan & status

- [x] **P0** Characterization + proof tests.
- [x] **P1** `getTabbableElements` deep walker (`focus-utils.js`).
- [x] **P2** Route `OlDialog` + `OlPopover` discovery through `getTabbableFromSlot`.
- [x] **P3** Slim `FocusableHostMixin` to `delegatesFocus`-only (drop host
      `tabindex`; the deep walker now finds the inner focusable directly). Also
      fixes the native-tab double-stop for mixin components used outside dialogs.
- [ ] **P4** Reusable roving-tabindex controller; migrate `OlSegmentedControl` +
      `OlPagination`.
- [ ] **P5** Enhancements (feature-detected): `inert` background guard,
      `:focus-visible` audit.
- [ ] **P6** Docs polish + regression guard (fail if a mixin component carries a
      host `tabindex`) + cross-browser matrix.

Each phase is independently shippable and revertable. P2 was the high-risk gate
(shared trap); P3 depends on P2 (only the deep walker can find a shadow-internal
focusable once the host loses its `tabindex`).
