/**
 * Keyboard list-navigation helpers for composite widgets.
 *
 * Separate from focus-utils.js (which is about *discovering* focusables for a
 * Tab trap): this computes where Arrow / Home / End keys should move within an
 * ordered set of items. It's a pure function so it serves two different models
 * with the same tested logic:
 *
 *   - Roving-tabindex composites (e.g. <ol-segmented-control>): one tab stop,
 *     arrows move the active item (wrap, both orientations).
 *   - Plain arrow-navigable lists (e.g. <ol-pagination>): every item is its own
 *     tab stop, arrows are a convenience that moves focus (no wrap, horizontal).
 */

function firstEnabled(count, isDisabled) {
    for (let i = 0; i < count; i++) if (!isDisabled(i)) return i;
    return -1;
}

function lastEnabled(count, isDisabled) {
    for (let i = count - 1; i >= 0; i--) if (!isDisabled(i)) return i;
    return -1;
}

// Step `dir` (+1/-1) from `current`, skipping disabled items. With `wrap`,
// continues past the ends; otherwise returns -1 when it would step out of
// bounds. Returns -1 if no enabled item is reachable.
function step(count, current, dir, isDisabled, wrap) {
    let i = current;
    for (let n = 0; n < count; n++) {
        i += dir;
        if (i < 0 || i >= count) {
            if (!wrap) return -1;
            i = (i + count) % count;
        }
        if (!isDisabled(i)) return i;
    }
    return -1;
}

/**
 * Destination index for an arrow-key navigation keypress.
 *
 * @param {string} key - `KeyboardEvent.key`.
 * @param {object} opts
 * @param {number} opts.count - Total number of items.
 * @param {number} opts.current - Index currently active/focused (`-1` if none).
 * @param {(i: number) => boolean} [opts.isDisabled] - Items to skip.
 * @param {'horizontal'|'vertical'|'both'} [opts.orientation='both'] - Which
 *   arrow axes navigate. Off-axis arrows are ignored (return `-1`).
 * @param {boolean} [opts.wrap=true] - Wrap around past the first/last item.
 * @returns {number} Destination index, or `-1` if the key isn't a navigation
 *   key for this config or there's no reachable target (caller should no-op).
 */
export function getNextIndex(key, { count, current, isDisabled = () => false, orientation = 'both', wrap = true }) {
    if (count <= 0) return -1;
    if (key === 'Home') return firstEnabled(count, isDisabled);
    if (key === 'End') return lastEnabled(count, isDisabled);

    const horizontal = orientation === 'horizontal' || orientation === 'both';
    const vertical = orientation === 'vertical' || orientation === 'both';
    const forward = (horizontal && key === 'ArrowRight') || (vertical && key === 'ArrowDown');
    const backward = (horizontal && key === 'ArrowLeft') || (vertical && key === 'ArrowUp');
    if (!forward && !backward) return -1;

    return step(count, current, forward ? 1 : -1, isDisabled, wrap);
}
