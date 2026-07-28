/**
 * Body scroll-lock utilities for full-viewport overlays (modals, mobile trays).
 *
 * The native `<dialog>.showModal()` blocks focus and clicks on the background but
 * does NOT prevent background touch-scroll on iOS Safari. Pinning <body> with
 * `position: fixed` and restoring the scroll offset on release is the reliable
 * cross-browser fix (the same technique used by Vaul / Radix / body-scroll-lock).
 *
 * Locks are reference-counted so stacked overlays compose: the body stays locked
 * until every holder releases it. The scroll offset is captured on the first lock
 * and restored on the last unlock. Callers should track whether they hold a lock
 * (so they unlock exactly once) rather than relying on the counter directly.
 */

let lockCount = 0;
let savedScrollY = 0;
let savedBodyStyle = null;

/**
 * Freezes background scroll by pinning <body> at its current scroll offset.
 * Safe to call when a lock is already held — increments the reference count.
 */
export function lockBodyScroll() {
    if (lockCount++ > 0) return;

    savedScrollY = window.scrollY;
    savedBodyStyle = {
        position: document.body.style.position,
        top: document.body.style.top,
        left: document.body.style.left,
        right: document.body.style.right,
        width: document.body.style.width,
        overflow: document.body.style.overflow,
    };
    document.body.style.position = 'fixed';
    document.body.style.top = `-${savedScrollY}px`;
    document.body.style.left = '0';
    document.body.style.right = '0';
    document.body.style.width = '100%';
    document.body.style.overflow = 'hidden';
}

/**
 * Releases one scroll lock. When the last holder releases, restores the original
 * <body> styles and the pre-lock scroll position. No-op if nothing is locked.
 */
export function unlockBodyScroll() {
    if (lockCount === 0) return;
    if (--lockCount > 0) return;

    if (savedBodyStyle) {
        Object.assign(document.body.style, savedBodyStyle);
        savedBodyStyle = null;
    }
    window.scrollTo(0, savedScrollY);
    savedScrollY = 0;
}
