/**
 * "Browse the stacks" on the home page: a grid of genre tiles that open a shelf
 * (subgenre chips + carousels) in place. The shelf HTML comes from
 * /partials/HomeGenre.json; its carousels are the same lazy placeholders the
 * rest of the home page uses, so lazy-carousel.js fills and controls them.
 */

import { trackEvent } from './ol.analytics.js';
import { buildPartialsUrl } from './utils';

/**
 * @param {HTMLElement} root - `.browse-stacks` section
 */
export function initBrowseStacks(root) {
    const shelf = root.querySelector('.browse-stacks__shelf');
    const tiles = Array.from(root.querySelectorAll('.browse-stacks__tile'));
    const i18n = JSON.parse(root.dataset.i18n || '{}');
    let current = null;
    let controller = null;

    function tileFor(slug) {
        return tiles.find(tile => tile.dataset.genre === slug);
    }

    function markExpanded(slug) {
        tiles.forEach(tile => tile.setAttribute('aria-expanded', String(tile.dataset.genre === slug)));
    }

    function close({ returnFocus = true } = {}) {
        controller?.abort();
        const tile = tileFor(current);
        current = null;
        markExpanded(null);
        shelf.hidden = true;
        shelf.innerHTML = '';
        if (returnFocus) tile?.focus();
    }

    async function load(slug, subgenre = '') {
        controller?.abort();
        controller = new AbortController();
        shelf.hidden = false;
        shelf.setAttribute('aria-busy', 'true');
        shelf.classList.add('browse-stacks__shelf--loading');
        try {
            const resp = await fetch(buildPartialsUrl('HomeGenre', { genre: slug, subgenre }), { signal: controller.signal });
            if (!resp.ok) throw new Error('Failed to fetch genre shelf');
            const data = await resp.json();
            shelf.innerHTML = data.partials;
            bindShelf(slug);
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
                load(slug, subgenre);
            });
            return false;
        } finally {
            shelf.classList.remove('browse-stacks__shelf--loading');
            shelf.removeAttribute('aria-busy');
        }
    }

    function bindShelf(slug) {
        shelf.querySelector('.genre-shelf__close')?.addEventListener('click', () => {
            trackEvent('BrowseStacks', 'Close', slug);
            close();
        });
        shelf.querySelectorAll('ol-chip[data-subgenre]').forEach(chip => {
            chip.addEventListener('ol-chip-select', (e) => {
                const subgenre = e.detail.selected ? chip.dataset.subgenre : '';
                trackEvent('BrowseStacks', subgenre ? 'Subgenre' : 'ClearSubgenre', `${slug}/${chip.dataset.subgenre}`);
                load(slug, subgenre);
            });
        });
    }

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
        shelf.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
        shelf.querySelector('.genre-shelf__title')?.focus({ preventScroll: true });
    }

    tiles.forEach(tile => tile.addEventListener('click', () => open(tile.dataset.genre)));

    // Document-level so Escape still works after a carousel refetch drops focus to <body>.
    // A popover inside the shelf owns its own Escape (its host is the retargeted event target).
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || !current || e.defaultPrevented) return;
        if (e.target.closest?.('ol-menu-popover, ol-popover, ol-select-popover, ol-options-popover')) return;
        close();
    });
}
