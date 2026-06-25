/**
 * Focus management utilities for web components with shadow DOM.
 */

/**
 * CSS selector for commonly focusable elements.
 * Excludes elements with tabindex="-1" which are programmatically focusable only.
 */
export const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * Gets the currently focused element, traversing through shadow DOM boundaries.
 * Useful when you need to find the actual focused element inside shadow roots.
 *
 * @returns {Element|null} The deepest active element, or null if nothing is focused
 *
 * @example
 * // If focus is inside a web component's shadow DOM:
 * // document.activeElement might return the host element,
 * // but getDeepActiveElement() returns the actual focused input/button inside.
 * const focused = getDeepActiveElement();
 */
export function getDeepActiveElement() {
    let active = document.activeElement;
    while (active?.shadowRoot?.activeElement) {
        active = active.shadowRoot.activeElement;
    }
    return active;
}

/**
 * Whether an element should participate in a focus trap. Excludes disabled
 * elements and elements that aren't currently rendered (e.g. `display: none`,
 * `visibility: hidden`). Calling `.focus()` on a non-rendered element is a
 * silent no-op in browsers — including such elements in a trap list causes
 * Tab/Shift+Tab to appear stuck on the prior element.
 *
 * @param {HTMLElement} el
 * @returns {Boolean}
 */
export function isFocusable(el) {
    if (el.disabled) return false;
    // checkVisibility() is widely supported in evergreen browsers (Chrome 105+,
    // Safari 17.4+, Firefox 125+) and is the correct API for "would the user
    // be able to focus this." Where unavailable (older jsdom, ancient browsers)
    // we err on the side of inclusion — the same behavior we had before.
    if (typeof el.checkVisibility === 'function') {
        return el.checkVisibility({ visibilityProperty: true });
    }
    return true;
}

/**
 * Collect tabbable elements under `root`, in depth-first DOM order, piercing
 * shadow roots and expanding slots — i.e. the real Tab order the user sees,
 * which `querySelectorAll` alone can't produce because it stops at shadow
 * boundaries.
 *
 * This is the discovery backbone for the manual focus trap: it works on any
 * shadow-DOM-v1 browser without relying on `delegatesFocus`, so the trap can
 * focus the *real* inner element directly rather than a host whose
 * `host.focus()` might delegate to a hidden element (a silent no-op).
 *
 * Traversal rules:
 *  - A `<slot>` contributes its flattened assigned elements, in slot order.
 *  - An element matching {@link FOCUSABLE_SELECTOR} is a **leaf tab stop**:
 *    recorded, and *not* descended into. A composite that owns its own
 *    keyboard nav (roving tabindex, arrow keys) must therefore expose exactly
 *    one Tab stop (its single `tabindex="0"`); we don't enumerate its items.
 *  - A non-matching element with an open `shadowRoot` is descended into (the
 *    shadow tree, whose `<slot>`s pull in light children at their position).
 *  - A non-matching element without a shadow root has its light children
 *    walked.
 *  - Hidden/disabled subtrees (see {@link isFocusable}) are skipped entirely.
 *  - Closed shadow roots (e.g. `<video controls>`) are opaque and skipped.
 *
 * @param {Element|ShadowRoot} root - Subtree to search.
 * @returns {HTMLElement[]} Tabbable elements in DOM order.
 */
export function getTabbableElements(root) {
    const out = [];
    if (root) walkTabbables(root, out);
    return out;
}

/**
 * Like {@link getTabbableElements} but seeded from a `<slot>`'s assigned
 * (light-DOM) content — for a focus trap that walks a component's named slots
 * (header/body/footer) rather than one subtree. Each assigned element is
 * visited with the same depth-first, shadow-piercing rules, so a custom element
 * sitting in slotted content contributes its real inner focusable rather than
 * being missed (which a one-slot-deep `querySelectorAll` scan would).
 *
 * @param {HTMLSlotElement|null} slot
 * @returns {HTMLElement[]} Tabbable elements in DOM order.
 */
export function getTabbableFromSlot(slot) {
    if (!slot) return [];
    const out = [];
    for (const el of slot.assignedElements({ flatten: true })) {
        visitTabbable(el, out);
    }
    return out;
}

// Record `el` if it's a tab stop, then decide whether to descend.
//
// FOCUSABLE_SELECTOR matches a native control (e.g. `button`) regardless of
// tabindex, so a roving composite's `tabindex="-1"` items would slip through —
// exclude them explicitly so a composite exposes only its single `tabindex="0"`
// stop.
//
// Descent rule (mirrors native sequential focus navigation):
//  - A tab stop that has a shadow root is a self-contained custom element that
//    owns its internal focus (delegatesFocus / arrow-key routing) — treat it as
//    a single leaf and do NOT enumerate its shadow guts.
//  - Any other element is descended into: a tab stop with light-DOM focusable
//    descendants contributes *both* (e.g. a `role="button" tabindex="0"` row
//    with a nested remove button), and a non-stop wrapper (incl. `tabindex=-1`)
//    contributes its descendants.
function visitTabbable(el, out) {
    if (!isFocusable(el)) return; // skip hidden/disabled subtrees entirely
    const isStop = el.matches?.(FOCUSABLE_SELECTOR) && el.getAttribute('tabindex') !== '-1';
    if (isStop) out.push(el);
    if (isStop && el.shadowRoot) return; // self-contained widget — leaf
    // Descend the shadow tree when present (its `<slot>`s pull light children
    // into place), otherwise the element's own light children.
    walkTabbables(el.shadowRoot ?? el, out);
}

// Walk a node's children in order, expanding any `<slot>` to its flattened
// assigned content (so projected light DOM is visited at the slot's position).
function walkTabbables(node, out) {
    for (const child of node.children) {
        if (child.localName === 'slot') {
            for (const assigned of child.assignedElements?.({ flatten: true }) ?? []) {
                visitTabbable(assigned, out);
            }
        } else {
            visitTabbable(child, out);
        }
    }
}

/**
 * Find the index of the focus-trap entry that owns the current focus, walking
 * up the DOM and across shadow boundaries. This lets a focus trap operate on
 * a host element (e.g. a custom-element wrapper around a deeper button) while
 * still recognizing the host as "current" when the inner element is focused.
 *
 * @param {HTMLElement[]} focusable - Trap-managed focusable elements
 * @param {Element|null} deepActive - Result of {@link getDeepActiveElement}
 * @returns {Number} Matching index, or -1
 */
export function findFocusableIndex(focusable, deepActive) {
    let el = deepActive;
    while (el) {
        const idx = focusable.indexOf(el);
        if (idx !== -1) return idx;
        // Climb out: first the regular parent chain, then jump over a shadow
        // boundary to the host element when we hit one.
        const parent = el.parentNode;
        if (parent && parent.nodeType === Node.DOCUMENT_FRAGMENT_NODE && parent.host) {
            el = parent.host;
        } else {
            el = el.parentElement;
        }
    }
    return -1;
}
