import { trackEvent } from '../ol.analytics.js';
import { buildPartialsUrl } from '../utils.js';

/**
 * Adds analytics and load-more to `<ol-carousel>` book rows, as Carousel.js does for slick rows.
 *
 * @param {Iterable<HTMLElement>} elems `ol-carousel` elements
 */
export function initNativeCarousels(elems) {
    elems.forEach((carousel) => {
        const config = JSON.parse(carousel.dataset.config || '{}');
        const category = config.analyticsCategory || 'Carousel';
        const key = config.carouselKey || '';

        carousel.addEventListener('ol-carousel-page-change', (e) => {
            if (e.detail.page > e.detail.previousPage) trackEvent(category, 'Next', key);
        });

        // The cover link is in ol-book-cover's shadow root, out of reach of `data-ol-link-track`.
        carousel.addEventListener('ol-book-cover-click', (e) => {
            const track = e.target.closest('[data-cover-track]')?.dataset.coverTrack;
            if (track) trackEvent(...track.split('|'));
        });

        const loadMore = config.loadMore;
        if (!loadMore?.queryType) return;
        let locked = false;
        let allDone = carousel.children.length < loadMore.limit;
        carousel.addEventListener('ol-carousel-near-end', async(e) => {
            if (locked || allDone) return;
            locked = true;
            trackEvent(category, 'LoadMore', key);
            carousel.setAttribute('aria-busy', 'true');
            try {
                const cards = await fetchMoreCards(loadMore, e.detail.itemCount);
                if (!cards.length) allDone = true;
                carousel.append(...cards);
            } catch {
                // The next near-end event retries.
            } finally {
                locked = false;
                carousel.removeAttribute('aria-busy');
            }
        });
    });
}

/**
 * @param {object} loadMore the `loadMore` block of the row's config
 * @param {number} itemCount cards already in the rail
 * @returns {Promise<Element[]>}
 */
async function fetchMoreCards(loadMore, itemCount) {
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
    });
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('Failed to fetch more carousel cards');
    const data = await resp.json();
    const template = document.createElement('template');
    template.innerHTML = (data.partials || []).join('');
    return Array.from(template.content.children);
}
