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

    // Filter out disabled elements
    return focusable.filter(el => !el.disabled);
}
