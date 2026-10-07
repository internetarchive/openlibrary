/**
 * "Browse the stacks" on the home page: a rail of genre tiles that open a shelf (a header for the
 * genre, its carousel, then one per subgenre) in place. The shelf HTML comes from /partials/HomeGenre.json
 * with the genre row already loaded and the subgenre rows as lazy placeholders; lazy-carousel.js loads
 * those and runs the header's sort control, which re-sorts the whole shelf. The first tile's shelf (Trending,
 * which the template pins first) is open on load; a caret on an open shelf points at its tile.
 * Opening another stack puts it in the URL (?stack=horror, replacing the history entry), so a reader who
 * follows a book and comes back finds it open: the template's inline script moves that tile into view and
 * draws its skeleton, and this opens it. Closing, or opening the pinned stack, clears the URL again.
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
    const skeleton = root.querySelector('.browse-stacks__loading')?.content;
    let current = null;
    let controller = null;
    let scroller = null;

    function tileFor(slug) {
        return tiles.find(tile => tile.dataset.genre === slug);
    }

    /** The stack the URL names: the one to open on load. */
    function requested() {
        return tileFor(new URLSearchParams(location.search).get('stack'));
    }

    /**
     * Keep the open stack in the URL so it survives a trip to a book page and back. The pinned (default)
     * stack and a closed shelf leave the URL clean.
     * @param {string|null} slug
     */
    function remember(slug) {
        const url = new URL(location.href);
        const tile = tileFor(slug);
        if (tile && !tile.hasAttribute('data-pinned')) {
            url.searchParams.set('stack', slug);
        } else {
            url.searchParams.delete('stack');
        }
        if (url.href !== location.href) history.replaceState(history.state, '', url);
    }

    function markExpanded(slug) {
        tiles.forEach(tile => tile.setAttribute('aria-expanded', String(tile.dataset.genre === slug)));
    }

    /**
     * Point the shelf's caret at the open tile, fading it over the tile's last half-width of travel
     * so it is gone before it reaches the rail's edge.
     * Where scroll-driven animations exist, CSS moves and fades the caret along the tile's view timeline,
     * so it scrolls in the same frame as the tile; --caret-from/--caret-to are the timeline's ends.
     * Elsewhere --caret-x and --caret-opacity are re-measured each scroll frame, a frame or so behind.
     */
    function anchor() {
        const tile = tileFor(current);
        if (!tile || shelf.hidden) {
            shelf.classList.remove('browse-stacks__shelf--anchored');
            return;
        }
        const tileRect = tile.getBoundingClientRect();
        const port = (scroller || rail).getBoundingClientRect();
        const shelfLeft = shelf.getBoundingClientRect().left;
        const centre = tileRect.left + tileRect.width / 2;
        const half = tile.offsetWidth / 2;
        shelf.style.setProperty('--caret-x', `${centre - shelfLeft}px`);
        shelf.style.setProperty('--caret-opacity', Math.max(0, Math.min(1, Math.min(centre - port.left, port.right - centre) / half)));
        if (scroller) {
            // The timeline runs from the tile entering at the scrollport's end edge to leaving at its start.
            const rtl = getComputedStyle(rail).direction === 'rtl';
            shelf.style.setProperty('--caret-from', `${(rtl ? port.left - half : port.right + half) - shelfLeft}px`);
            shelf.style.setProperty('--caret-to', `${(rtl ? port.right + half : port.left - half) - shelfLeft}px`);
        }
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
        remember(null);
        shelf.hidden = true;
        shelf.innerHTML = '';
        anchor();
        if (returnFocus) tile?.focus();
    }

    /**
     * The shelf's skeleton: the header naming the tile's genre, its subgenres as the "Jump to" line and
     * a stub for its sort control; then the genre row, titled; then a row per subgenre, so the loaded shelf
     * lands in the same shape. The template's inline script builds the same for the shelf open on load.
     * @param {HTMLElement} tile
     * @returns {DocumentFragment}
     */
    function skeletonFor(tile) {
        const fragment = skeleton ? skeleton.cloneNode(true) : document.createDocumentFragment();
        const [genreRow, subgenreRow] = fragment.querySelectorAll('.carousel-skeleton');
        if (!genreRow) return fragment;
        const data = JSON.parse(tile.dataset.shelf);
        const entitle = (row, name) => {
            row.querySelector('.carousel-skeleton__title').textContent = name;
        };
        fragment.querySelector('.genre-shelf__title').textContent = data.name;
        const jump = fragment.querySelector('.genre-shelf__jump');
        if (data.subgenres.length) {
            jump.append(...data.subgenres.map(name => Object.assign(document.createElement('span'), { textContent: name })));
        } else {
            jump.remove();
        }
        entitle(genreRow, data.title);
        data.subgenres.forEach(name => {
            const row = subgenreRow.cloneNode(true);
            entitle(row, name);
            subgenreRow.before(row);
        });
        subgenreRow.remove();
        return fragment;
    }

    /**
     * @param {string} slug
     * @param {object} [options]
     * @param {boolean} [options.initial] - the shelf opened on load, whose skeleton the template's inline script already drew
     */
    async function load(slug, { initial = false } = {}) {
        controller?.abort();
        controller = new AbortController();
        const { signal } = controller;
        shelf.setAttribute('aria-busy', 'true');
        if (!initial || shelf.hidden) {
            shelf.hidden = false;
            shelf.replaceChildren(skeletonFor(tileFor(slug)));
            shelf.classList.add('browse-stacks__shelf--loading');
        }
        const lazyCarouselModule = import('./lazy-carousel');
        // The template's inline script already started the fetch for the shelf open on load.
        const prefetch = shelf.prefetch;
        delete shelf.prefetch;
        try {
            const resp = await (initial && prefetch?.slug === slug
                ? prefetch.response
                : fetch(buildPartialsUrl('HomeGenre', { genre: slug }), { signal }));
            if (!resp.ok) throw new Error('Failed to fetch genre shelf');
            const [data, lazyCarousel] = await Promise.all([resp.json(), lazyCarouselModule]);
            if (signal.aborted) return false;
            shelf.innerHTML = data.partials;
            lazyCarousel.initLoadedCarousels(shelf);
            lazyCarousel.initLazyCarousel(shelf.querySelectorAll('.lazy-carousel'));
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
            // Unless a newer load owns the shelf's busy state now.
            if (controller.signal === signal) {
                shelf.classList.remove('browse-stacks__shelf--loading');
                shelf.removeAttribute('aria-busy');
            }
        }
    }

    /**
     * @param {string} slug
     * @param {object} [options]
     * @param {boolean} [options.initial] - the shelf opened on load, not by the reader: don't focus or track it
     */
    async function open(slug, { initial = false } = {}) {
        if (current === slug) {
            close();
            return;
        }
        current = slug;
        markExpanded(slug);
        if (!initial) {
            remember(slug);
            trackEvent('BrowseStacks', 'Open', slug);
        }
        // The skeleton is already the loaded shelf's size, so point at it while it loads.
        // No scrolling: the shelf opens right under the rail, and the page stays where the reader is.
        const loading = load(slug, { initial });
        anchor();
        const ok = await loading;
        if (!ok || current !== slug) return;
        anchor();
        if (!initial) shelf.querySelector('.genre-shelf')?.focus({ preventScroll: true });
    }

    tiles.forEach(tile => tile.addEventListener('click', () => open(tile.dataset.genre)));

    // Lead with the URL's stack open, or else the first tile's (Trending; the template's inline script
    // already drew the same shelf's skeleton).
    const first = requested() || tiles[0];
    if (first) open(first.dataset.genre, { initial: true });

    // The scroller is inside ol-carousel's shadow root; scroll events don't cross it.
    customElements.whenDefined('ol-carousel').then(() => rail.updateComplete).then(() => {
        scroller = rail.shadowRoot?.querySelector('.viewport');
        scroller?.addEventListener('scroll', track, { passive: true });
        anchor();
    });
    rail.addEventListener('ol-carousel-page-change', anchor);
    window.addEventListener('resize', anchor);

    // Only Escape from inside the stacks, so dismissing the header search or a menu leaves the shelf open.
    // A popover inside the shelf owns its own Escape (its host is the retargeted event target).
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || !current || e.defaultPrevented) return;
        if (!e.composedPath().includes(root)) return;
        if (e.target.closest?.('ol-menu-popover, ol-popover, ol-select-popover, ol-options-popover')) return;
        close();
    });
}
