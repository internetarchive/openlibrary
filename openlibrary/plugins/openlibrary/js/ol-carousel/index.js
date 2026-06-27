import { buildPartialsUrl } from '../utils.js';

/**
 * Load-more wiring for the <ol-carousel> web component.
 *
 * The <ol-carousel> component (openlibrary/components/lit/OlCarousel.js) handles
 * layout, paging, and swipe on its own. It does not know about books or how to
 * fetch more of them. This module bolts the existing carousel load-more pipeline
 * onto it: when the patron pages near the end, we fetch additional book cards
 * from the `CarouselLoadMore` partial and append them as slotted children. The
 * component observes `slotchange` and recomputes its pages automatically.
 *
 * Mirrors the behaviour of the Slick wrapper in js/carousel/Carousel.js.
 *
 * @param {NodeList<HTMLElement>|HTMLElement[]} elems  ol-carousel elements with a data-config attribute
 */
export function initOlCarousels(elems) {
    elems.forEach((elem) => {
        let config;
        try {
            config = JSON.parse(elem.dataset.config || '{}');
        } catch {
            return;
        }

        const loadMore = Object.assign(
            { limit: 18, pageMode: 'offset', locked: false, allDone: false, page: 0 },
            config.loadMore || {}
        );

        // No load-more configured (or it lacks the required queryType): the
        // component still works as a static, pageable carousel.
        if (!loadMore.queryType) return;

        elem.addEventListener('ol-carousel-page-change', (ev) => {
            const { page, totalPages } = ev.detail;
            // Preload when within one page of the end.
            const nearEnd = totalPages - 1 - page <= 1;
            if (loadMore.locked || loadMore.allDone || !nearEnd) return;

            loadMore.locked = true;
            if (loadMore.pageMode === 'page') {
                loadMore.page++;
            } else {
                // Offset mode: start from the current number of cards.
                loadMore.page = elem.children.length;
            }
            fetchMore(elem, loadMore);
        });
    });
}

/**
 * Fetches the next batch of cards and appends them as slotted children.
 *
 * @param {HTMLElement} elem
 * @param {object} loadMore
 */
function fetchMore(elem, loadMore) {
    const url = buildPartialsUrl('CarouselLoadMore', {
        queryType: loadMore.queryType,
        q: loadMore.q,
        limit: loadMore.limit,
        page: loadMore.page,
        sorts: loadMore.sorts,
        subject: loadMore.subject,
        pageMode: loadMore.pageMode,
        hasFulltextOnly: loadMore.hasFulltextOnly,
        secondaryAction: loadMore.secondaryAction,
        key: loadMore.key,
        ...(loadMore.extraParams || {}),
    });

    fetch(url)
        .then((resp) => {
            if (!resp.ok) throw new Error('Failed to fetch carousel partials');
            return resp.json();
        })
        .then((results) => {
            const cards = results.partials || [];
            if (!cards.length) {
                loadMore.allDone = true;
            } else {
                appendCards(elem, cards);
            }
            loadMore.locked = false;
        })
        .catch(() => {
            // Unlock so a later page-change can retry.
            loadMore.locked = false;
        });
}

/**
 * Parses card HTML strings and appends them as direct children of the carousel.
 *
 * @param {HTMLElement} elem
 * @param {string[]} cards  HTML strings, each a single book card
 */
function appendCards(elem, cards) {
    const fragment = document.createDocumentFragment();
    const parser = document.createElement('div');
    cards.forEach((html) => {
        parser.innerHTML = html.trim();
        // Each partial is a single card element; move its children over.
        while (parser.firstElementChild) {
            fragment.appendChild(parser.firstElementChild);
        }
    });
    elem.appendChild(fragment);
}
