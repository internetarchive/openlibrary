/**
 * Wires the availability toggle + language filter popover on the search results
 * page (openlibrary/templates/work_search.html). They render empty from the
 * template; this module seeds them with the current selection, navigates to an
 * updated /search URL when a filter changes, and keeps the cross-page
 * sticky-filter state in sessionStorage so the header search modal and the
 * search-page filters stay in sync.
 *
 * Persistence model — URL is the source of truth on /search:
 *
 *  - On init, if the URL carries any filter param (availability params or
 *    `language`), sessionStorage is mirrored from the URL. This way the modal
 *    will reflect a filter change made via the toggle, the language popover, or
 *    the sidebar language facet (which navigates the page with a new `language=`
 *    param) the next time it opens.
 *
 *  - On init, if the URL carries NO filter params and sessionStorage has a
 *    non-default value, we replace-navigate to /search with those sticky
 *    filters applied. This handles arriving at /search from a search box
 *    submit on another page or from `?q=foo` typed straight into the address
 *    bar — the user gets the filters they last set in this session.
 *
 * The full language catalogue is fetched lazily on first popover open.
 */

import {
    AVAILABILITY_TO_PARAMS,
    DEFAULT_AVAILABILITY,
    DEFAULT_LANGUAGE_OPTIONS,
    SS_AVAILABILITY_KEY,
    SS_LANGUAGES_KEY,
    ssGet,
    ssSet,
    availabilityFromParams,
    readStoredLanguages,
} from './search-modal/constants.js';
import { fetchLanguageOptions } from './search-modal/languages.js';

// Every query param the availability filter owns, across all of its values.
// Cleared before applying a new value so stale availability filters don't
// accumulate in the URL.
const AVAILABILITY_PARAM_KEYS = [
    ...new Set(Object.values(AVAILABILITY_TO_PARAMS).flatMap(Object.keys)),
];

function writeStoredAvailability(value) {
    ssSet(SS_AVAILABILITY_KEY, value || DEFAULT_AVAILABILITY);
}

function writeStoredLanguages(values) {
    ssSet(SS_LANGUAGES_KEY, JSON.stringify(values || []));
}

// ── URL / sticky-filter helpers ────────────────────────────────────────────

function urlHasAnyFilterParam(params) {
    if (AVAILABILITY_PARAM_KEYS.some(k => params.has(k))) return true;
    if (params.has('language')) return true;
    return false;
}

/**
 * Mirror the current URL's filter state to sessionStorage so the modal opens
 * with the same selection next time. We always write both keys so removing a
 * filter via the popovers/sidebar clears the stored value too.
 */
function syncSessionStorageFromUrl(params) {
    writeStoredAvailability(availabilityFromParams(name => params.get(name)));
    writeStoredLanguages(params.getAll('language'));
}

/**
 * If the URL has no filter params at all and sessionStorage has a non-default
 * value, replace-navigate to /search with the sticky filters applied. Returns
 * true when a navigation was kicked off (caller should stop further init).
 *
 * `replace` is used so the unfiltered URL doesn't end up in the back-stack.
 */
function maybeApplyStickyFilters(params) {
    if (urlHasAnyFilterParam(params)) return false;

    const storedAvail = ssGet(SS_AVAILABILITY_KEY) || DEFAULT_AVAILABILITY;
    const storedLangs = readStoredLanguages();
    if (storedAvail === DEFAULT_AVAILABILITY && storedLangs.length === 0) {
        return false;
    }

    const next = new URLSearchParams(params);
    const mapped = AVAILABILITY_TO_PARAMS[storedAvail] || {};
    Object.entries(mapped).forEach(([key, value]) => next.set(key, value));
    storedLangs.forEach(code => next.append('language', code));
    window.location.replace(`/search?${next.toString()}`);
    return true;
}

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
    const currentParams = new URLSearchParams(window.location.search);

    // Sticky-filter handoff: if the URL has no filter params, apply whatever
    // the modal/popovers last stored. Returns true when it triggered a
    // replace-navigation; bail out so we don't bind handlers on a page that's
    // about to unload.
    if (maybeApplyStickyFilters(currentParams)) return;

    // URL is now the source of truth — mirror it into sessionStorage so the
    // modal sees the same filters next time it opens. Has to run *before* the
    // popovers are seeded so a stale sessionStorage doesn't leak into them.
    syncSessionStorageFromUrl(currentParams);

    const availabilityEl = container.querySelector('ol-toggle');
    const languageEl = container.querySelector('ol-select-popover');

    if (availabilityEl) {
        // Binary availability: the toggle reads as "on" whenever any
        // readable-scoped filter is in the URL (readable / open / borrowable),
        // and "off" for the all-books default. Flipping it on applies the broad
        // `readable` filter; flipping it off clears every availability param.
        availabilityEl.checked =
            availabilityFromParams((name) => currentParams.get(name)) !== DEFAULT_AVAILABILITY;
        availabilityEl.addEventListener('ol-toggle-change', (e) => {
            const value = e.detail.checked ? 'readable' : DEFAULT_AVAILABILITY;
            writeStoredAvailability(value);
            const mapped = AVAILABILITY_TO_PARAMS[value] || {};
            navigateWithParams((params) => {
                AVAILABILITY_PARAM_KEYS.forEach((key) => params.delete(key));
                Object.entries(mapped).forEach(([key, val]) => params.set(key, val));
            });
        });
        // The readable-count sublabel is rendered server-side (work_search.html),
        // so it's already present on first paint — nothing to fetch here.
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
            writeStoredLanguages(e.detail.selected);
            navigateWithParams((params) => {
                params.delete('language');
                e.detail.selected.forEach((code) => params.append('language', code));
            });
        });
    }
}
