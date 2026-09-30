/**
 * Top-layer promotion for anchored overlay panels (popovers, tooltips).
 *
 * Overlay panels are positioned from viewport coordinates read off the
 * trigger's `getBoundingClientRect()`. Plain `position: fixed` looks like the
 * right way to paint them, but a fixed element's containing block is the
 * nearest *transformed* ancestor rather than the viewport — and `transform`,
 * `filter`, `perspective`, `backdrop-filter`, `contain` and `will-change` all
 * create one. Inside a carousel track (or any such container) the panel is
 * measured against the wrong origin and lands hundreds of pixels off its
 * trigger, clipped by the container's bounds.
 *
 * The top layer sidesteps all of it: its containing block is always the
 * viewport, and it paints above the page regardless of ancestor
 * `isolation: isolate` or z-index stacking.
 *
 * Browsers without the Popover API (Safari < 17) keep the plain
 * `position: fixed` path, which is correct everywhere except under one of
 * those containing-block ancestors.
 *
 * Two UA-stylesheet behaviours callers must handle in their own CSS and
 * sequencing:
 *
 * 1. `[popover]` is `display: none` until shown — promote a panel *before*
 *    measuring it, or `offsetWidth`/`offsetHeight` read 0.
 * 2. The UA sets `inset: 0`, `margin: auto`, `width`/`height: fit-content`,
 *    `border`, `padding`, `overflow` and system colors on `[popover]`. Author
 *    styles win by cascade origin, but only for properties they actually
 *    declare — anything left undeclared silently inherits the UA value. The
 *    `fit-content` sizing in particular beats `inset: 0`, collapsing a
 *    full-viewport overlay to 0x0.
 */

/** Whether the browser supports the Popover API (Chrome 114, Safari 17, Firefox 125). */
export const SUPPORTS_TOP_LAYER =
    typeof HTMLElement !== 'undefined' &&
    typeof HTMLElement.prototype.showPopover === 'function';

/**
 * The `popover` attribute value to render on a promotable panel, or `undefined`
 * when the browser lacks support (so no attribute is emitted).
 *
 * Always `manual`, never `auto`: `auto` brings light-dismiss and force-closes
 * sibling popovers outside the ancestor chain, which would collapse a
 * component's own nesting and dismissal handling.
 *
 * @returns {String|undefined}
 */
export function topLayerAttr() {
    return SUPPORTS_TOP_LAYER ? 'manual' : undefined;
}

/**
 * Show `el` in the top layer, tolerating the states that make `showPopover()`
 * throw (already showing, not connected to the document).
 *
 * @param {Element|null|undefined} el
 */
export function promoteToTopLayer(el) {
    if (!SUPPORTS_TOP_LAYER || !el || !el.isConnected) return;
    if (el.matches(':popover-open')) return;
    try {
        el.showPopover();
    } catch {
        // Not promotable (disconnected mid-flight) — the position: fixed
        // fallback still paints it correctly off a transform.
    }
}

/**
 * Drop `el` out of the top layer, tolerating an already-hidden element.
 *
 * @param {Element|null|undefined} el
 */
export function demoteFromTopLayer(el) {
    if (!SUPPORTS_TOP_LAYER || !el || !el.isConnected) return;
    if (!el.matches(':popover-open')) return;
    try {
        el.hidePopover();
    } catch {
        // Already hidden, e.g. by removal from the DOM.
    }
}
