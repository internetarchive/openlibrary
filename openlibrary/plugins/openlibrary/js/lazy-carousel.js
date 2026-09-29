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
                bindControls(newElem);

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
 * Wires the header controls (the readable-only toggle) of a
 * loaded carousel. Each change rewrites the stored config and refetches the
 * whole carousel, so the server re-renders the controls in their new state.
 *
 * @param host {HTMLElement} `.lazy-carousel-loaded` wrapper carrying `data-config`
 */
function bindControls(host) {
    const controls = host.querySelector('.carousel-controls');
    if (!controls) return;
    const config = JSON.parse(host.dataset.config);
    const label = config.key || config.title || '';

    controls.querySelector('.carousel-controls__readable')?.addEventListener('ol-toggle-change', (e) => {
        config.has_fulltext_only = e.detail.checked;
        trackEvent('Carousel', e.detail.checked ? 'ReadableOn' : 'ReadableOff', label);
        refetch(host, config);
    });
}

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
    // The control that triggered this is about to be re-rendered; find its successor by class.
    const active = document.activeElement;
    const activeControl = host.contains(active) && Array.from(active.classList).find(cls => cls.startsWith('carousel-controls__'));

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
            bindControls(host);
            if (activeControl) host.querySelector(`.${activeControl}`)?.focus();
        })
        .catch(() => {
            // Keep the current cards; the controls still reflect the last successful state.
        })
        .finally(() => {
            host.classList.remove('lazy-carousel-loaded--refreshing');
            host.removeAttribute('aria-busy');
        });
}
