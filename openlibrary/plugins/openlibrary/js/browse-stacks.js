/**
 * "Browse the stacks" on the home page: a rail of genre tiles that open a shelf
 * (a carousel for the genre, with a subgenre control that narrows it) in place. The shelf HTML comes from
 * /partials/HomeGenre.json; its carousels are the same lazy placeholders the
 * rest of the home page uses, so lazy-carousel.js fills and controls them.
 * No shelf is open on load; a caret on an open shelf points at its tile.
 */

import { trackEvent } from './ol.analytics.js';
import { buildPartialsUrl } from './utils';

/**
 * @param {HTMLElement} root - `.browse-stacks` section
 */
export function initBrowseStacks(root) {
    const rail = root.querySelector('.browse-stacks__rail');
    const shelf = root.querySelector('.browse-stacks__shelf');
    const tiles = Array.from(root.querySelectorAll('.browse-stacks__tile'));
    const i18n = JSON.parse(root.dataset.i18n || '{}');
    let current = null;
    let controller = null;
    let scroller = null;

    function tileFor(slug) {
        return tiles.find(tile => tile.dataset.genre === slug);
    }

    function markExpanded(slug) {
        tiles.forEach(tile => tile.setAttribute('aria-expanded', String(tile.dataset.genre === slug)));
    }

    /**
     * Point the shelf's caret at the open tile, and fade it once the tile's centre leaves the rail.
     * Where scroll-driven animations exist, CSS moves the caret along the tile's view timeline,
     * so it scrolls in the same frame as the tile; --caret-from/--caret-to are the timeline's ends.
     * Elsewhere --caret-x is re-measured each scroll frame, a frame or so behind.
     */
    function anchor() {
        const tile = tileFor(current);
        if (!tile || shelf.hidden) {
            shelf.classList.remove('browse-stacks__shelf--anchored');
            return;
        }
        const tileRect = tile.getBoundingClientRect();
        const railRect = rail.getBoundingClientRect();
        const shelfLeft = shelf.getBoundingClientRect().left;
        const centre = tileRect.left + tileRect.width / 2;
        shelf.style.setProperty('--caret-x', `${centre - shelfLeft}px`);
        if (scroller) {
            // The timeline runs from the tile entering at the scrollport's end edge to leaving at its start.
            const port = scroller.getBoundingClientRect();
            const half = tile.offsetWidth / 2;
            const rtl = getComputedStyle(rail).direction === 'rtl';
            shelf.style.setProperty('--caret-from', `${(rtl ? port.left - half : port.right + half) - shelfLeft}px`);
            shelf.style.setProperty('--caret-to', `${(rtl ? port.right + half : port.left - half) - shelfLeft}px`);
        }
        shelf.classList.toggle('browse-stacks__shelf--caret-out', centre < railRect.left || centre > railRect.right);
        shelf.classList.add('browse-stacks__shelf--anchored');
    }

    // While the rail scrolls, the caret follows each frame instead of easing after the tile.
    // Settles on a short idle rather than scrollend, which Safari only got in 26.2.
    let frame = 0;
    let idle = 0;
    function track() {
        shelf.classList.add('browse-stacks__shelf--tracking');
        clearTimeout(idle);
        idle = setTimeout(settle, 150);
        if (frame) return;
        frame = requestAnimationFrame(() => {
            frame = 0;
            anchor();
        });
    }
    function settle() {
        shelf.classList.remove('browse-stacks__shelf--tracking');
        anchor();
    }

    function close({ returnFocus = true } = {}) {
        controller?.abort();
        const tile = tileFor(current);
        current = null;
        markExpanded(null);
        shelf.hidden = true;
        shelf.innerHTML = '';
        anchor();
        if (returnFocus) tile?.focus();
    }

    async function load(slug) {
        controller?.abort();
        controller = new AbortController();
        shelf.hidden = false;
        shelf.setAttribute('aria-busy', 'true');
        shelf.classList.add('browse-stacks__shelf--loading');
        try {
            const resp = await fetch(buildPartialsUrl('HomeGenre', { genre: slug }), { signal: controller.signal });
            if (!resp.ok) throw new Error('Failed to fetch genre shelf');
            const data = await resp.json();
            shelf.innerHTML = data.partials;
            const placeholders = shelf.querySelectorAll('.lazy-carousel');
            if (placeholders.length) {
                import('./lazy-carousel').then(module => module.initLazyCarousel(placeholders));
            }
            return true;
        } catch (e) {
            if (e.name === 'AbortError') return false;
            shelf.innerHTML = `<p class="genre-shelf__error"><a href="#" class="genre-shelf__retry">${i18n.error || 'Try again?'}</a></p>`;
            shelf.querySelector('.genre-shelf__retry').addEventListener('click', (ev) => {
                ev.preventDefault();
                load(slug);
            });
            return false;
        } finally {
            shelf.classList.remove('browse-stacks__shelf--loading');
            shelf.removeAttribute('aria-busy');
        }
    }

    /**
     * @param {string} slug
     */
    async function open(slug) {
        if (current === slug) {
            close();
            return;
        }
        current = slug;
        markExpanded(slug);
        trackEvent('BrowseStacks', 'Open', slug);
        const ok = await load(slug);
        if (!ok || current !== slug) return;
        anchor();
        shelf.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
        shelf.querySelector('.genre-shelf')?.focus({ preventScroll: true });
    }

    tiles.forEach(tile => tile.addEventListener('click', () => open(tile.dataset.genre)));

    // The scroller is inside ol-carousel's shadow root; scroll events don't cross it.
    customElements.whenDefined('ol-carousel').then(() => rail.updateComplete).then(() => {
        scroller = rail.shadowRoot?.querySelector('.viewport');
        scroller?.addEventListener('scroll', track, { passive: true });
        anchor();
    });
    rail.addEventListener('ol-carousel-page-change', anchor);
    window.addEventListener('resize', anchor);

    // Document-level so Escape still works after a carousel refetch drops focus to <body>.
    // A popover inside the shelf owns its own Escape (its host is the retargeted event target).
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || !current || e.defaultPrevented) return;
        if (e.target.closest?.('ol-menu-popover, ol-popover, ol-select-popover, ol-options-popover')) return;
        close();
    });
}
