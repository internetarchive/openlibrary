// Auto-hides the site header (IA bar + OL nav, wrapped as #site-header-autohide -- see
// openlibrary/templates/site/body.html) on scroll-down, reveals it again on scroll-up or
// once back near the top. The wrapper itself (position: sticky) and the .header-hidden
// transform live in static/css/components/header-bar.css; this only toggles the class.

// Ignore scroll deltas smaller than this so a tiny wheel tick or trackpad jitter doesn't
// flicker the header.
const HIDE_THRESHOLD_PX = 8;
// Always show the header once within this many px of the top, regardless of direction --
// covers the "scrolled down a little, then a little more" case where a strict delta check
// alone would leave it hidden right at the top of the page.
const REVEAL_NEAR_TOP_PX = 40;

/**
 * @param {HTMLElement} header The #site-header-autohide wrapper.
 * @param {Window | HTMLElement} scrollable Element whose scroll position drives the
 *   show/hide -- window for a normal page, or a specific internal scroll container (e.g.
 *   Genre Explorer's .book-room, which captures all scrolling itself so window.scrollY
 *   never changes on that page).
 * @param {(hidden: boolean) => void} [onToggle] Called whenever the hidden state actually
 *   changes. The header hides via `transform` (not `max-height`/`display`, which would
 *   need `overflow: hidden` and clip the header's own dropdowns -- language picker,
 *   Browse menu -- when open) so it never reclaims its layout space on its own. That's
 *   invisible on a normal page (the header was already scrolled-past, so content below it
 *   already occupies that space) but not on Genre Explorer's fixed-height pane, which
 *   never scrolls the *document* at all -- this callback is how BookRoom.vue grows/shifts
 *   its own pane to fill the gap the header leaves when hidden.
 * @returns {() => void} Teardown function that removes the scroll listener.
 */
export function initHeaderAutoHide(header, scrollable = window, onToggle) {
    const getScrollPos = () => (scrollable === window ? window.scrollY : scrollable.scrollTop);

    let lastScrollPos = getScrollPos();
    let ticking = false;
    let hidden = false;

    function setHidden(next) {
        if (next === hidden) return;
        hidden = next;
        header.classList.toggle('header-hidden', hidden);
        onToggle?.(hidden);
    }

    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            const pos = getScrollPos();
            const delta = pos - lastScrollPos;
            if (pos <= REVEAL_NEAR_TOP_PX) {
                setHidden(false);
            } else if (delta > HIDE_THRESHOLD_PX) {
                setHidden(true);
            } else if (delta < -HIDE_THRESHOLD_PX) {
                setHidden(false);
            }
            lastScrollPos = pos;
            ticking = false;
        });
    }

    scrollable.addEventListener('scroll', onScroll, { passive: true });
    return () => scrollable.removeEventListener('scroll', onScroll);
}
