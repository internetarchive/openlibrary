import {initialzeCarousels} from './carousel';
import { buildPartialsUrl } from './utils';

let relatedBooksTracked = false;
let bannerClicked = false;

document.addEventListener('click', (e) => {
    if (e.target.closest('a[data-ol-link-track="OpenRelatedBooks|BannerClick"]')) {
        bannerClicked = true;
    }
});

/**
 * Adds functionality that allows carousels to lazy-load when a patron
 * scrolls near any of the given elements
 *
 * @param elems {NodeList<HTMLElement>} Collection of placeholder carousel elements
 */
export function initLazyCarousel(elems) {
    // Create intersection observer
    const intersectionObserver = new IntersectionObserver(intersectionCallback, {
        root: null,
        rootMargin: '200px',
        threshold: 0
    });

    elems.forEach(elem => {
        // Observe element for intersections
        intersectionObserver.observe(elem);

        // Add retry listener
        const retryElem = elem.querySelector('.retry-btn');
        retryElem.addEventListener('click', (e) => {
            e.preventDefault();
            handleRetry(elem);
        });
    });
}

/**
 * Prepares and makes a request for carousel HTML
 *
 * @param data {object}
 * @returns {Promise<Response>}
 */
async function fetchPartials(data) {
    return fetch(buildPartialsUrl('LazyCarousel', {...data}));
}

/**
 * Attempts to fetch HTML for a single carousel, and updates the view
 * with the results.
 *
 * If the request is successful, the given `target` element is replaced
 * by the carousel.  Otherwise, a retry button is presented to the patron.
 *
 * On retry, this function is called again.
 *
 * @param target {HTMLElement} A placeholder element for a carousel
 */
function doFetchAndUpdate(target) {
    const config = JSON.parse(target.dataset.config);
    const loadingIndicator = target.querySelector('.loadingIndicator');

    fetchPartials(config)
        .then(resp => {
            if (!resp.ok) {
                throw new Error('Failed to fetch partials from server');
            }
            return resp.json();
        })
        .then(data => {
            const newElem = document.createElement('div');
            newElem.innerHTML = data.partials.trim();
            const carouselElements = newElem.querySelectorAll('.carousel--progressively-enhanced');
            loadingIndicator.classList.add('hidden');

            if (carouselElements.length === 0 && config.fallback) {
                // No results, disable filters
                if (typeof config.fallback === 'string') {
                    config.query = config.fallback;
                }
                config.has_fulltext_only = false;
                config.fallback = false; // Prevents infinite retries
                target.dataset.config = JSON.stringify(config);

                target.querySelector('.lazy-carousel-fallback').classList.remove('hidden');
            } else {
                target.parentNode.insertBefore(newElem, target);
                target.remove();
                initialzeCarousels(carouselElements);

                // ==========================================
                // EXPERIMENT TRACKING: Related Books Discovery
                // Tracks natural scrolling vs banner clicks.
                // Can be safely deleted no problems
                // ==========================================
                if (config.key === 'related-subjects-carousel' || config.key === 'related-authors-carousel') {
                    const body = document.getElementById('contentBody');
                    const lendingState = body ? body.getAttribute('data-lending-state') : null;
                    const unavailableStates = ['preview_only', 'checkedout', 'waitlist', 'locate'];
                    const isUnavailable = unavailableStates.indexOf(lendingState) !== -1;

                    let action;
                    if (bannerClicked) {
                        action = 'FromBanner';
                    } else if (isUnavailable) {
                        action = 'ScrolledDownUnavailable';
                    } else {
                        action = 'ScrolledDownAvailable';
                    }

                    if (!relatedBooksTracked && window.archive_analytics && window.archive_analytics.ol_send_event_ping) {
                        window.archive_analytics.ol_send_event_ping({
                            category: 'OpenRelatedBooks',
                            action: action,
                            label: lendingState,
                        });
                        relatedBooksTracked = true;
                    }
                }
            }
        })
        .catch(() => {
            loadingIndicator.classList.add('hidden');
            const retryElem = target.querySelector('.lazy-carousel-retry');
            retryElem.classList.remove('hidden');
        });
}

/**
 * Shows loading indicator, hides retry element, and attempts to
 * fetch data and update the view again.
 *
 * @param target {Element}
 */
function handleRetry(target) {
    target.querySelector('.loadingIndicator').classList.remove('hidden');
    target.querySelector('.lazy-carousel-retry').classList.add('hidden');
    const carouselFallbackElem = target.querySelector('.lazy-carousel-fallback');
    if (carouselFallbackElem) {
        carouselFallbackElem.classList.add('hidden');
    }
    doFetchAndUpdate(target);
}

/**
 * Callback used by the lazy-loaded carousel intersection observer.
 *
 * Unregisters target from observer and fetches carousel HTML.
 *
 * @param entries {Array<IntersectionObserverEntry>}
 * @param observer {IntersectionObserver}
 */
function intersectionCallback(entries, observer) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const target = entry.target;
            observer.unobserve(target);
            doFetchAndUpdate(target);
        }
    });
}
