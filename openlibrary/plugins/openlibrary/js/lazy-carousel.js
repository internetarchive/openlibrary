import {initialzeCarousels} from './carousel';
import { initNativeCarousels } from './carousel/native.js';
import { trackEvent } from './ol.analytics.js';
import {
    getGlobalPreferences,
    mapPreferencesToBackend,
    onGlobalPreferencesChange,
    setGlobalPreferences,
    updateAllCarousels,
} from './preferences';
import { buildPartialsUrl, whenVisible } from './utils';

let relatedBooksTracked = false;
let bannerClicked = false;

// A loaded row is either a slick carousel or the native component (books/custom_carousel.html.jinja).
const CAROUSEL_SELECTOR = '.carousel--progressively-enhanced, ol-carousel';

function initCarousels(elems) {
    const slick = [];
    const native = [];
    elems.forEach((elem) => (elem.localName === 'ol-carousel' ? native : slick).push(elem));
    initialzeCarousels(slick);
    initNativeCarousels(native);
}

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
            const carouselElements = newElem.querySelectorAll(CAROUSEL_SELECTOR);
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
            } else if (carouselElements.length === 0 && config.readable_filter) {
                // Empty on first load, but the Readable-online switch may fill it: keep it hidden until it does.
                newElem.dataset.config = JSON.stringify(config);
                newElem.dataset.hideWhenEmpty = '';
                newElem.hidden = true;
                target.parentNode.insertBefore(newElem, target);
                target.remove();
            } else if (carouselElements.length === 0) {
                // Nothing to show on first load: drop the row (with its controls) rather than
                // announcing an empty shelf the patron never asked for.
                target.remove();
            } else {
                // The loaded wrapper keeps the config so its header controls can refetch in place.
                newElem.dataset.config = JSON.stringify(config);
                target.parentNode.insertBefore(newElem, target);
                target.remove();
                initCarousels(carouselElements);

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
 * The page's Readable-online switch, if this page has one (home/readable_filter.html.jinja).
 * Carousels rendered with `readable_filter` in their config follow it. The patron's choice
 * is kept in preferences.js: restored here before any carousel fetches, stored when the
 * switch changes, and broadcast as `global-preferences-changed` so every carousel (and
 * any other tab) follows.
 */
const readableSwitch = document.querySelector('.readable-filter__toggle');

function applyReadableSwitch(config) {
    if (config.readable_filter && readableSwitch) {
        config.has_fulltext_only = readableSwitch.checked;
    }
    return config;
}

if (readableSwitch) {
    readableSwitch.checked = mapPreferencesToBackend(getGlobalPreferences()).hasFulltextOnly;

    readableSwitch.addEventListener('ol-toggle-change', (e) => {
        trackEvent('ReadableFilter', e.detail.checked ? 'On' : 'Off', 'home');
        setGlobalPreferences({ mode: e.detail.checked ? 'fulltext' : 'all' });
        updateAllCarousels();
    });

    // The preference changed in another tab.
    onGlobalPreferencesChange(() => updateAllCarousels());

    document.addEventListener('global-preferences-changed', (e) => {
        const readable = mapPreferencesToBackend(e.detail).hasFulltextOnly;
        readableSwitch.checked = readable;
        document.querySelectorAll('.lazy-carousel-loaded[data-config], .lazy-carousel[data-config]').forEach((host) => {
            const config = JSON.parse(host.dataset.config);
            if (!config.readable_filter || config.has_fulltext_only === readable) return;
            config.has_fulltext_only = readable;
            if (host.classList.contains('lazy-carousel-loaded')) {
                refetch(host, config);
            } else {
                // Not fetched yet (below the fold): it picks the new state up when it loads.
                host.dataset.config = JSON.stringify(config);
            }
        });
    });
}

/**
 * A row's sort control (`sort_control` in its config; books/custom_carousel.html.jinja)
 * refetches that row in place with the chosen sort.
 */
document.addEventListener('ol-menu-popover-select', (e) => {
    const control = e.target.closest?.('.carousel-sort');
    const host = control?.closest('.lazy-carousel-loaded[data-config]');
    if (!host) return;
    const config = JSON.parse(host.dataset.config);
    // The menu fires for the current item too.
    if (e.detail.value === config.sort) return;
    trackEvent('CarouselSort', e.detail.value, config.key);
    // The menu hands focus back to its trigger only once it finishes closing, which can be
    // after the refetch lands, so name the control to refocus rather than reading focus.
    refetch(host, { ...config, sort: e.detail.value }, '.carousel-sort');
});

/**
 * A genre row's subgenre control (`genre` in its config; HomeGenrePartial) narrows the row to
 * one subgenre, or widens it back with "All".
 */
document.addEventListener('ol-segmented-control-change', (e) => {
    const control = e.target.closest?.('.carousel-subgenres');
    const host = control?.closest('.lazy-carousel-loaded[data-config]');
    if (!host) return;
    const config = JSON.parse(host.dataset.config);
    const subgenre = e.detail.value === 'all' ? '' : e.detail.value;
    trackEvent('CarouselSubgenre', subgenre || 'All', config.key);
    refetch(host, { ...config, subgenre });
});

// The latest refetch per carousel, so a slower earlier response can't overwrite a newer one.
const latestRefetch = new WeakMap();

/**
 * Replaces a loaded carousel with a fresh render for `config`. The old cards
 * stay visible, dimmed, until the new ones arrive; on failure they stay put.
 *
 * @param host {HTMLElement}
 * @param config {object}
 * @param [refocus] {string} selector of the control to focus after the re-render
 */
function refetch(host, config, refocus) {
    const previous = JSON.parse(host.dataset.config);
    const request = {};
    latestRefetch.set(host, request);
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
            if (latestRefetch.get(host) !== request) return;
            // The header re-renders too; keep focus on the control that had it.
            const focusedControl = refocus || (host.querySelector('.carousel-subgenres')?.matches(':focus-within') && '.carousel-subgenres');
            host.innerHTML = data.partials.trim();
            const carouselElements = host.querySelectorAll(CAROUSEL_SELECTOR);
            if ('hideWhenEmpty' in host.dataset) host.hidden = carouselElements.length === 0;
            initCarousels(carouselElements);
            const control = focusedControl ? host.querySelector(focusedControl) : null;
            if (control?.matches('.carousel-sort')) {
                const trigger = control.querySelector(':scope > [slot="trigger"]');
                trigger?.updateComplete.then(() => trigger.focus());
            } else if (control) {
                control.updateComplete.then(() => control.renderRoot.querySelector('.segment[aria-checked="true"]')?.focus());
            }
        })
        .catch(() => {
            if (latestRefetch.get(host) !== request) return;
            // Keep the current cards, and put the controls back to the state they show.
            host.dataset.config = JSON.stringify(previous);
            const sort = host.querySelector('.carousel-sort');
            if (sort) sort.value = previous.sort;
            const subgenres = host.querySelector('.carousel-subgenres');
            if (subgenres) subgenres.value = previous.subgenre || 'all';
        })
        .finally(() => {
            if (latestRefetch.get(host) !== request) return;
            host.classList.remove('lazy-carousel-loaded--refreshing');
            host.removeAttribute('aria-busy');
        });
}
