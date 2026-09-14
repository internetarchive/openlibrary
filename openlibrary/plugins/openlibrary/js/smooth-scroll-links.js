/**
 * Smooth scrolling for same-page links marked `data-ol-smooth-scroll`.
 * @module smooth-scroll-links
 */

/** Clearing mid-animation doesn't cut the scroll short, so this needn't outlast it. */
const RESET_FALLBACK_MS = 500;

/**
 * Makes each link's fragment jump animate. The page has no global
 * `scroll-behavior: smooth`, so links opt in individually.
 *
 * @param {NodeListOf<HTMLAnchorElement>} links
 */
export function initSmoothScrollLinks(links) {
    for (const link of links) {
        link.addEventListener('click', () => {
            if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
            // Smooth only for this jump, keeping native hash handling (history, :target,
            // focus). Chrome reads it on a later frame, so clear it once the scroll ends.
            const root = document.documentElement;
            root.style.scrollBehavior = 'smooth';
            const reset = () => {
                clearTimeout(timer);
                document.removeEventListener('scrollend', reset);
                root.style.scrollBehavior = '';
            };
            // Fallback for no scroll (target already in view) and Safari < 26.2 (no scrollend).
            const timer = setTimeout(reset, RESET_FALLBACK_MS);
            document.addEventListener('scrollend', reset);
        });
    }
}
