/**
 * "Browse the stacks" on the home page: genre tiles that open a shelf in place, from /partials/HomeGenre.json.
 * The open stack is kept in ?stack= so it survives a trip to a book page and back.
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

    function requested() {
        return tileFor(new URLSearchParams(location.search).get('stack'));
    }

    /** @param {string|null} slug - null, or the pinned stack, clears ?stack= */
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
     * Point the shelf's caret at the open tile, fading it out near the rail's edges.
     * With scroll-driven animations CSS moves it between --caret-from/--caret-to; elsewhere we re-measure per frame.
     */
    function anchor() {
        const tile = tileFor(current);
        // Until ol-carousel upgrades there's no viewport to measure against; drawing early parks the caret top-left.
        if (!tile || shelf.hidden || !scroller) {
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
            const rtl = getComputedStyle(rail).direction === 'rtl';
            shelf.style.setProperty('--caret-from', `${(rtl ? port.left - half : port.right + half) - shelfLeft}px`);
            shelf.style.setProperty('--caret-to', `${(rtl ? port.right + half : port.left - half) - shelfLeft}px`);
        }
        shelf.classList.add('browse-stacks__shelf--anchored');
    }

    // Idle timeout rather than scrollend, which Safari only got in 26.2.
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
        trackEvent('BrowseStacks', 'Close', current);
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
     * A skeleton in the loaded shelf's shape. Keep in sync with the inline script in browse_stacks.html.jinja.
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
     * @param {boolean} [options.initial] - opened on load; the inline script already drew the skeleton
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
            trackEvent('BrowseStacks', 'LoadError', slug);
            shelf.innerHTML = `<p class="genre-shelf__error"><a href="#" class="genre-shelf__retry">${i18n.error || 'Try again?'}</a></p>`;
            shelf.querySelector('.genre-shelf__retry').addEventListener('click', (ev) => {
                ev.preventDefault();
                trackEvent('BrowseStacks', 'Retry', slug);
                load(slug);
            });
            return false;
        } finally {
            if (controller.signal === signal) {
                shelf.classList.remove('browse-stacks__shelf--loading');
                shelf.removeAttribute('aria-busy');
            }
        }
    }

    /**
     * @param {string} slug
     * @param {object} [options]
     * @param {boolean} [options.initial] - opened on load, not by the reader: don't focus or track it
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
        const loading = load(slug, { initial });
        anchor();
        const ok = await loading;
        if (!ok || current !== slug) return;
        anchor();
        if (!initial) shelf.querySelector('.genre-shelf')?.focus({ preventScroll: true });
    }

    tiles.forEach(tile => tile.addEventListener('click', () => open(tile.dataset.genre)));

    const first = requested() || tiles[0];
    if (first) open(first.dataset.genre, { initial: true });

    // Scroll events don't cross ol-carousel's shadow root.
    customElements.whenDefined('ol-carousel').then(() => rail.updateComplete).then(() => {
        scroller = rail.shadowRoot?.querySelector('.viewport');
        scroller?.addEventListener('scroll', track, { passive: true });
        anchor();
    });
    rail.addEventListener('ol-carousel-page-change', (e) => {
        anchor();
        // Labelled with the page reached (1-based), to see how far into the genres readers look.
        if (e.detail.page > e.detail.previousPage) trackEvent('BrowseStacks', 'RailNext', String(e.detail.page + 1));
    });
    window.addEventListener('resize', anchor);

    // Escape only from inside the stacks, and not from a popover, which handles its own.
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || !current || e.defaultPrevented) return;
        if (!e.composedPath().includes(root)) return;
        if (e.target.closest?.('ol-menu-popover, ol-popover, ol-select-popover, ol-options-popover')) return;
        close();
    });
}
