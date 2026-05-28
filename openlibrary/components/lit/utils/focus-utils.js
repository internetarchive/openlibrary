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
 * Gets all focusable elements from a slot's assigned content.
 * Handles both elements that are directly focusable and their focusable descendants.
 *
 * @param {HTMLSlotElement} slot - The slot element to get focusable elements from
 * @returns {HTMLElement[]} Array of focusable elements in DOM order
 *
 * @example
 * const slot = this.renderRoot.querySelector('slot');
 * const focusable = getFocusableFromSlot(slot);
 */
export function getFocusableFromSlot(slot) {
    if (!slot) return [];

    const focusable = [];
    const assignedElements = slot.assignedElements({ flatten: true });

    for (const el of assignedElements) {
        // Check if the element itself is focusable
        if (el.matches?.(FOCUSABLE_SELECTOR)) {
            focusable.push(el);
        }
        // Find focusable descendants
        focusable.push(...el.querySelectorAll(FOCUSABLE_SELECTOR));
    }

    return focusable.filter(isFocusable);
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
