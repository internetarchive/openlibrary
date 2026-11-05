import { trackEvent } from '../ol.analytics.js';
import { buildPartialsUrl } from '../utils.js';

/** @type {WeakMap<HTMLElement, (detail: {yearFrom: number, yearTo: number}) => void>} */
const filterHandlers = new WeakMap();
let filterListening = false;

/**
 * Adds analytics, load-more, and the publishing-history year filter to `<ol-carousel>` book rows.
 *
 * @param {Iterable<HTMLElement>} elems `ol-carousel` elements
 */
export function initNativeCarousels(elems) {
    // Sent by the publishing-history chart (publishing_history.js) when a year range is picked.
    // One shared listener, so rows replaced by a refetch can be garbage collected.
    if (!filterListening) {
        filterListening = true;
        document.addEventListener('filter', e => {
            document.querySelectorAll('ol-carousel').forEach(carousel => filterHandlers.get(carousel)?.(e.detail));
        });
    }
    elems.forEach(carousel => {
        const config = JSON.parse(carousel.dataset.config || '{}');
        const category = config.analyticsCategory || 'Carousel';
        const key = config.carouselKey || '';

        carousel.addEventListener('ol-carousel-page-change', e => {
            if (e.detail.page > e.detail.previousPage) trackEvent(category, 'Next', key);
        });

        // The cover link is in ol-book-cover's shadow root, out of reach of `data-ol-link-track`.
        carousel.addEventListener('ol-book-cover-click', e => {
            const track = e.target.closest('[data-cover-track]')?.dataset.coverTrack;
            if (track) trackEvent(...track.split('|'));
        });

        // On touch the caption is the visible link; show the loading state on its cover.
        carousel.addEventListener('click', e => {
            const caption = e.target.closest('.carousel-caption');
            if (!caption || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            const cover = caption.closest('.book')?.querySelector('ol-book-cover');
            if (cover) cover.loading = true;
        });

        const loadMore = config.loadMore;
        if (!loadMore?.queryType) return;
        let allDone = carousel.children.length < loadMore.limit;
        let extraParams = {};
        // The in-flight load-more or filter; a newer filter supersedes either.
        let pending = null;

        const start = () => {
            const request = {};
            pending = request;
            carousel.setAttribute('aria-busy', 'true');
            return request;
        };
        const finish = request => {
            if (request !== pending) return false;
            pending = null;
            carousel.removeAttribute('aria-busy');
            return true;
        };

        carousel.addEventListener('ol-carousel-near-end', async () => {
            if (pending || allDone) return;
            trackEvent(category, 'LoadMore', key);
            const request = start();
            try {
                const cards = await fetchMoreCards(loadMore, carousel.children.length, extraParams);
                if (request !== pending) return;
                if (!cards.length) allDone = true;
                carousel.append(...cards);
            } catch {
                // The next near-end event retries.
            } finally {
                finish(request);
            }
        });

        filterHandlers.set(carousel, async ({ yearFrom, yearTo }) => {
            const params = { published_in: `${yearFrom}-${yearTo}` };
            const request = start();
            try {
                const cards = await fetchMoreCards(loadMore, 0, params);
                if (request !== pending) return;
                extraParams = params;
                allDone = cards.length < loadMore.limit;
                carousel.replaceChildren(...cards);
                carousel.goToPage(0);
            } catch {
                // Keep the current cards.
            } finally {
                // A near-end swallowed while this was in flight, or a same-size swap, won't re-fire on its own.
                if (finish(request)) carousel.resetNearEnd();
            }
        });
    });
}

/**
 * @param {object} loadMore the `loadMore` block of the row's config
 * @param {number} itemCount cards already in the rail
 * @param {object} [extraParams] e.g. the year filter's `published_in`
 * @returns {Promise<Element[]>}
 */
async function fetchMoreCards(loadMore, itemCount, extraParams = {}) {
    const url = buildPartialsUrl('CarouselLoadMore', {
        queryType: loadMore.queryType,
        q: loadMore.q,
        limit: loadMore.limit,
        page: itemCount,
        sorts: loadMore.sorts,
        subject: loadMore.subject,
        pageMode: 'offset',
        hasFulltextOnly: loadMore.hasFulltextOnly,
        secondaryAction: loadMore.secondaryAction,
        layout: loadMore.layout,
        key: loadMore.key,
        ...extraParams
    });
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('Failed to fetch more carousel cards');
    const data = await resp.json();
    const template = document.createElement('template');
    template.innerHTML = (data.partials || []).join('');
    return Array.from(template.content.children);
}
