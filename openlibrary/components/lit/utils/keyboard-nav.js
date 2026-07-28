/**
 * Keyboard list-navigation helpers for composite widgets. Computes where Arrow /
 * Home / End should move within an ordered set of items; the caller owns focus.
 *
 * Separate from focus-utils.js, which discovers focusables for a Tab trap.
 */

/**
 * @callback IsDisabled
 * @param {number} index
 * @returns {boolean}
 */

/**
 * First index that isn't disabled.
 *
 * @param {number} count
 * @param {IsDisabled} isDisabled
 * @returns {number} Index, or -1 if every item is disabled.
 */
function firstEnabled(count, isDisabled) {
    for (let i = 0; i < count; i++) if (!isDisabled(i)) return i;
    return -1;
}

/**
 * Last index that isn't disabled.
 *
 * @param {number} count
 * @param {IsDisabled} isDisabled
 * @returns {number} Index, or -1 if every item is disabled.
 */
function lastEnabled(count, isDisabled) {
    for (let i = count - 1; i >= 0; i--) if (!isDisabled(i)) return i;
    return -1;
}

/**
 * Step one place from `current` in direction `dir`, skipping disabled items.
 *
 * @param {number} count
 * @param {number} current
 * @param {1|-1} dir
 * @param {IsDisabled} isDisabled
 * @param {boolean} wrap - Continue past the ends rather than stopping.
 * @returns {number} Destination index, or -1 if out of bounds (without `wrap`)
 *   or no enabled item is reachable.
 */
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
 * Serves both models with the same logic: roving-tabindex composites
 * (`<ol-segmented-control>`: one tab stop, arrows move the active item, wrap) and
 * plain arrow-navigable lists (`<ol-pagination>`: every item its own tab stop,
 * arrows move focus, no wrap).
 *
 * @param {string} key - `KeyboardEvent.key`.
 * @param {object} opts
 * @param {number} opts.count - Total number of items.
 * @param {number} opts.current - Index currently active/focused (`-1` if none).
 * @param {IsDisabled} [opts.isDisabled] - Items to skip.
 * @param {'horizontal'|'vertical'|'both'} [opts.orientation='both'] - Which arrow
 *   axes navigate. Off-axis arrows are ignored.
 * @param {boolean} [opts.wrap=true] - Wrap past the first/last item.
 * @returns {number} Destination index, or -1 if the key isn't a navigation key
 *   for this config or there's no reachable target (caller should no-op).
 */
export function getNextKeyboardFocusIndex(key, { count, current, isDisabled = () => false, orientation = 'both', wrap = true }) {
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
