/**
 * Wires the availability + language filter popovers on the search results page
 * (openlibrary/templates/work_search.html). The popovers render empty from the
 * template; this module seeds them with options and the current selection (read
 * from the URL query), and navigates to an updated /search URL when a filter
 * changes. The full language catalogue is fetched lazily, only once the
 * language popover is first opened.
 *
 * Filter values live entirely in the URL query string, so the language popover
 * and the sidebar language facet (which reloads the page with a new `language=`
 * param when clicked) stay in sync automatically through a full page load.
 */

import {
    AVAILABILITY_TO_PARAMS,
    DEFAULT_LANGUAGE_OPTIONS,
    availabilityFromParams,
    availabilityOptionsFromElement,
} from './search-modal/constants.js';
import { fetchLanguageOptions } from './search-modal/languages.js';

// Every query param the availability filter owns, across all of its values.
// Cleared before applying a new value so stale availability filters don't
// accumulate in the URL.
const AVAILABILITY_PARAM_KEYS = [
    ...new Set(Object.values(AVAILABILITY_TO_PARAMS).flatMap(Object.keys)),
];

/**
 * Navigate to /search with the current query string mutated by `mutate`.
 * Pagination is reset because the result set changes.
 * @param {(params: URLSearchParams) => void} mutate
 */
function navigateWithParams(mutate) {
    const params = new URLSearchParams(window.location.search);
    mutate(params);
    params.delete('page');
    window.location.assign(`/search?${params.toString()}`);
}

/**
 * Fill in option lists and wire change handlers for the filter row.
 * @param {HTMLElement} container - the `.search-filter-row` element
 */
export function initSearchFilterBar(container) {
    const availabilityEl = container.querySelector('ol-options-popover');
    const languageEl = container.querySelector('ol-select-popover');
    const currentParams = new URLSearchParams(window.location.search);

    if (availabilityEl) {
        // Translated labels/descriptions are rendered into the container's
        // data-i18n attribute (search/availability_i18n.html); fall back to
        // English defaults if it's absent.
        availabilityEl.items = availabilityOptionsFromElement(container);
        availabilityEl.selected = availabilityFromParams((name) => currentParams.get(name));
        availabilityEl.addEventListener('ol-options-popover-change', (e) => {
            const mapped = AVAILABILITY_TO_PARAMS[e.detail.selected] || {};
            navigateWithParams((params) => {
                AVAILABILITY_PARAM_KEYS.forEach((key) => params.delete(key));
                Object.entries(mapped).forEach(([key, value]) => params.set(key, value));
            });
        });
    }

    if (languageEl) {
        // Seed with the curated defaults so a pre-selected language renders its
        // label immediately, without waiting on (or requiring) the network.
        languageEl.items = DEFAULT_LANGUAGE_OPTIONS;
        languageEl.selected = currentParams.getAll('language');

        // Defer fetching the full catalogue list until the popover first opens.
        // Most searches never touch the language filter, so this avoids the
        // /languages.json request entirely for them. ol-popover-open bubbles
        // (composed) out of the popover's shadow root up to this host.
        let languagesLoaded = false;
        languageEl.addEventListener('ol-popover-open', () => {
            if (languagesLoaded) return;
            languagesLoaded = true;
            fetchLanguageOptions().then((options) => {
                languageEl.items = options;
            });
        });

        languageEl.addEventListener('ol-select-popover-change', (e) => {
            navigateWithParams((params) => {
                params.delete('language');
                e.detail.selected.forEach((code) => params.append('language', code));
            });
        });
    }
}
