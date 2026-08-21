/**
 * Focus management utilities for web components with shadow DOM.
 *
 * `querySelectorAll` stops at shadow boundaries and `document.activeElement`
 * only reports the outer host, so a manual focus trap can't be written with
 * either. These helpers do the piercing that trap needs.
 */

/**
 * Commonly focusable elements. Excludes `tabindex="-1"` (programmatic focus only).
 *
 * @type {string}
 */
export const FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * The focused element, descending through shadow roots.
 *
 * @returns {Element|null} The deepest active element, or null if nothing is focused.
 */
export function getDeepActiveElement() {
    let active = document.activeElement;
    while (active?.shadowRoot?.activeElement) {
        active = active.shadowRoot.activeElement;
    }
    return active;
}

/**
 * Whether an element can participate in a focus trap. Excludes disabled and
 * non-rendered elements — `.focus()` on those is a silent no-op, which would
 * make Tab appear stuck on the previous element.
 *
 * @param {HTMLElement} el
 * @returns {boolean} True where `checkVisibility` is unavailable (older jsdom),
 *   erring toward inclusion.
 */
export function isFocusable(el) {
    if (el.disabled) return false;
    if (typeof el.checkVisibility === 'function') {
        return el.checkVisibility({ visibilityProperty: true });
    }
    return true;
}

/**
 * Collect tabbable elements under `root` in depth-first order, piercing shadow
 * roots and expanding slots — the real Tab order the user sees.
 *
 * A match on {@link FOCUSABLE_SELECTOR} is a leaf: composites owning their own
 * keyboard nav expose only their single `tabindex="0"` stop. Hidden/disabled
 * subtrees and closed shadow roots are skipped.
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
 * Like {@link getTabbableElements} but seeded from a `<slot>`'s assigned content
 * — for a trap that walks named slots (header/body/footer) rather than one
 * subtree. A custom element in slotted content contributes its real inner
 * focusable, which a one-slot-deep `querySelectorAll` would miss.
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

/**
 * Record `el` if it's a tab stop, then decide whether to descend. A tab stop
 * with a shadow root is a self-contained widget and treated as a leaf; anything
 * else is descended into, so a `tabindex="0"` row with a nested button
 * contributes both.
 *
 * @param {Element} el
 * @param {HTMLElement[]} out - Accumulator, mutated in place.
 * @returns {void}
 */
function visitTabbable(el, out) {
    if (!isFocusable(el)) return;
    // FOCUSABLE_SELECTOR matches native controls regardless of tabindex, so
    // exclude -1 explicitly or a roving composite's items would slip through.
    const isStop = el.matches?.(FOCUSABLE_SELECTOR) && el.getAttribute('tabindex') !== '-1';
    if (isStop) out.push(el);
    if (isStop && el.shadowRoot) return;
    walkTabbables(el.shadowRoot ?? el, out);
}

/**
 * Walk a node's children in order, expanding `<slot>`s to their flattened
 * assigned content so projected light DOM is visited at the slot's position.
 *
 * @param {Element|ShadowRoot} node
 * @param {HTMLElement[]} out - Accumulator, mutated in place.
 * @returns {void}
 */
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
 * Index of the trap entry owning the current focus, walking up through shadow
 * boundaries. Lets a trap hold a host element and still recognize it as current
 * when a deeper inner element is focused.
 *
 * @param {HTMLElement[]} focusable - Trap-managed focusable elements.
 * @param {Element|null} deepActive - Result of {@link getDeepActiveElement}.
 * @returns {number} Matching index, or -1.
 */
export function findFocusableIndex(focusable, deepActive) {
    let el = deepActive;
    while (el) {
        const idx = focusable.indexOf(el);
        if (idx !== -1) return idx;
        const parent = el.parentNode;
        if (parent && parent.nodeType === Node.DOCUMENT_FRAGMENT_NODE && parent.host) {
            el = parent.host;
        } else {
            el = el.parentElement;
        }
    }
    return -1;
}
