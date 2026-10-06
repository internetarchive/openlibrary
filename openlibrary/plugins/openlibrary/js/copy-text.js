/** Pending `.is-copied` resets, so a repeat click restarts the timer. */
const resetTimers = new WeakMap();

/**
 * Copy `text` and flag `trigger` with `.is-copied` briefly, which the
 * copy-button styles use to swap the copy glyph for a check.
 * @param {HTMLElement} trigger
 * @param {string} text
 */
export async function copyText(trigger, text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        return; // No clipboard permission — silently leave the page as it was.
    }

    trigger.classList.add('is-copied');
    clearTimeout(resetTimers.get(trigger));
    resetTimers.set(trigger, setTimeout(() => trigger.classList.remove('is-copied'), 1200));
}
