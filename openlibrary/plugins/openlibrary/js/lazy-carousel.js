import {initialzeCarousels} from './carousel';
import { trackEvent } from './ol.analytics.js';
import { buildPartialsUrl, whenVisible } from './utils';

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
    elems.forEach(elem => {
        whenVisible(elem).then(() => doFetchAndUpdate(elem));

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
    const config = applyReadableSwitch(JSON.parse(target.dataset.config));
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
            newElem.className = 'lazy-carousel-loaded';
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
            } else if (carouselElements.length === 0) {
                // Nothing to show on first load: drop the row (with its controls) rather than
                // announcing an empty shelf the patron never asked for.
                target.remove();
            } else {
                // The loaded wrapper keeps the config so its header controls can refetch in place.
                newElem.dataset.config = JSON.stringify(config);
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
 * The page's Readable-only switch, if this page has one (home/readable_filter.html.jinja).
 * Carousels rendered with `readable_filter` in their config follow it: the switch's state
 * is applied before their first fetch, and a change refetches every loaded one.
 */
const readableSwitch = document.querySelector('.readable-filter__toggle');

function applyReadableSwitch(config) {
    if (config.readable_filter && readableSwitch) {
        config.has_fulltext_only = readableSwitch.checked;
    }
    return config;
}

readableSwitch?.addEventListener('ol-toggle-change', (e) => {
    const readable = e.detail.checked;
    trackEvent('ReadableFilter', readable ? 'On' : 'Off', 'home');
    document.querySelectorAll('.lazy-carousel-loaded[data-config], .lazy-carousel[data-config]').forEach((host) => {
        const config = JSON.parse(host.dataset.config);
        if (!config.readable_filter) return;
        config.has_fulltext_only = readable;
        if (host.classList.contains('lazy-carousel-loaded')) {
            refetch(host, config);
        } else {
            // Not fetched yet (below the fold): it picks the new state up when it loads.
            host.dataset.config = JSON.stringify(config);
        }
    });
});

/**
 * Replaces a loaded carousel with a fresh render for `config`. The old cards
 * stay visible, dimmed, until the new ones arrive; on failure they stay put.
 *
 * @param host {HTMLElement}
 * @param config {object}
 */
function refetch(host, config) {
    host.dataset.config = JSON.stringify(config);
    host.classList.add('lazy-carousel-loaded--refreshing');
    host.setAttribute('aria-busy', 'true');

    fetchPartials(config)
        .then(resp => {
            if (!resp.ok) {
                throw new Error('Failed to fetch partials from server');
            }
            return resp.json();
        })
        .then(data => {
            host.innerHTML = data.partials.trim();
            initialzeCarousels(host.querySelectorAll('.carousel--progressively-enhanced'));
        })
        .catch(() => {
            // Keep the current cards; the controls still reflect the last successful state.
        })
        .finally(() => {
            host.classList.remove('lazy-carousel-loaded--refreshing');
            host.removeAttribute('aria-busy');
        });
}
