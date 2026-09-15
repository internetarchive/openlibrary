/**
 * Slot utilities for web components.
 */

/**
 * Checks if a slot has meaningful content (elements or non-empty text).
 * Useful for conditionally showing/hiding slot wrapper elements.
 *
 * Gotcha this exists for: whitespace between the tags counts as assigned to the
 * *default* slot, so `<ol-toast message="…">\n</ol-toast>` suppresses native
 * `<slot>` fallback. Track this from `@slotchange` and render fallback yourself.
 *
 * @param {HTMLSlotElement} slot - The slot element to check
 * @returns {boolean} True if the slot has content
 *
 * @example
 * // In a slotchange handler:
 * _handleSlotChange(event) {
 *     this.hasContent = slotHasContent(event.target);
 * }
 *
 */
export function slotHasContent(slot) {
    if (!slot) return false;
    const assignedNodes = slot.assignedNodes({ flatten: true });
    return assignedNodes.some(node => {
        if (node.nodeType === Node.ELEMENT_NODE) return true;
        if (node.nodeType === Node.TEXT_NODE) return node.textContent.trim() !== '';
        return false;
    });
}
