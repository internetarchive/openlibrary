/**
 * Wires the availability toggle + language filter popover on the search
 * results surfaces: /search (work_search.html) and /search/inside
 * (search/inside.html), each with its own URL-param dialect (see SURFACES).
 * The controls render empty from the template; this module seeds them with
 * the current selection, navigates to an updated URL on the same page when a
 * filter changes, and keeps the cross-page sticky-filter state in
 * sessionStorage so the header search modal and the page filters stay in sync.
 *
 * Persistence model — URL is the source of truth on these pages:
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
 * Context-aware facet counts are fetched in parallel with the catalogue
 * whenever there is an active search query. Counts and the merge into the
 * catalogue live in searchFacets.js, shared with the header search modal —
 * this file doesn't duplicate that logic.
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
import { fetchFacetCounts, mergeFacetCounts, openWhenCountsReady } from './search-modal/searchFacets.js';
import { trackEvent } from './ol.analytics.js';

// Every query param the availability filter owns, across all of its values.
// Cleared before applying a new value so stale availability filters don't
// accumulate in the URL.
const AVAILABILITY_PARAM_KEYS = [
    ...new Set(Object.values(AVAILABILITY_TO_PARAMS).flatMap(Object.keys)),
];

// Per-surface param dialects for the shared filter row. /search speaks Solr
// (has_fulltext/public_scan…); /search/inside speaks the FTS endpoint's single
// readable=true param — its collections can't split open vs borrowable, so any
// non-default stored availability maps to the broad readable filter there.
// facetCounts marks the surfaces whose results actually come from Solr:
// /search/facets.json counts Solr matches, which would misdescribe the FTS
// result set on /search/inside.
const SURFACES = {
    '/search': {
        readAvailability: (params) => availabilityFromParams((name) => params.get(name)),
        availabilityParamKeys: AVAILABILITY_PARAM_KEYS,
        availabilityParams: (value) => AVAILABILITY_TO_PARAMS[value] || {},
        facetCounts: true,
    },
    '/search/inside': {
        readAvailability: (params) =>
            params.get('readable') === 'true' ? 'readable' : DEFAULT_AVAILABILITY,
        availabilityParamKeys: ['readable'],
        availabilityParams: (value) =>
            value === DEFAULT_AVAILABILITY ? {} : { readable: 'true' },
        facetCounts: false,
    },
};

function currentSurface() {
    return SURFACES[window.location.pathname] || SURFACES['/search'];
}

// ── Facet field config ─────────────────────────────────────────────────────
//
// Maps each OlSelectPopover to its Solr facet field name (validated server-side
// against WorkSearchScheme.facet_fields).
/** @type {Map<HTMLElement, string>} */
let POPOVER_FIELD_CONFIG;

// ── sessionStorage helpers ─────────────────────────────────────────────────

function writeStoredAvailability(value) {
    ssSet(SS_AVAILABILITY_KEY, value || DEFAULT_AVAILABILITY);
}

function writeStoredLanguages(values) {
    ssSet(SS_LANGUAGES_KEY, JSON.stringify(values || []));
}

// ── URL / sticky-filter helpers ────────────────────────────────────────────

function urlHasAnyFilterParam(surface, params) {
    if (surface.availabilityParamKeys.some(k => params.has(k))) return true;
    if (params.has('language')) return true;
    return false;
}

/**
 * Mirror the current URL's filter state to sessionStorage so the modal opens
 * with the same selection next time. We always write both keys so removing a
 * filter via the popovers/sidebar clears the stored value too.
 */
function syncSessionStorageFromUrl(surface, params) {
    writeStoredAvailability(surface.readAvailability(params));
    writeStoredLanguages(params.getAll('language'));
}

/**
 * If the URL has no filter params at all and sessionStorage has a non-default
 * value, replace-navigate to /search with the sticky filters applied. Returns
 * true when a navigation was kicked off (caller should stop further init).
 *
 * `replace` is used so the unfiltered URL doesn't end up in the back-stack.
 */
function maybeApplyStickyFilters(surface, params) {
    if (urlHasAnyFilterParam(surface, params)) return false;

    const storedAvail = ssGet(SS_AVAILABILITY_KEY) || DEFAULT_AVAILABILITY;
    const storedLangs = readStoredLanguages();
    if (storedAvail === DEFAULT_AVAILABILITY && storedLangs.length === 0) {
        return false;
    }

    const next = new URLSearchParams(params);
    const mapped = surface.availabilityParams(storedAvail);
    Object.entries(mapped).forEach(([key, value]) => next.set(key, value));
    storedLangs.forEach(code => next.append('language', code));
    window.location.replace(`${window.location.pathname}?${next.toString()}`);
    return true;
}

/**
 * Navigate to the current page with the query string mutated by `mutate`.
 * Pagination is reset because the result set changes.
 * @param {(params: URLSearchParams) => void} mutate
 */
function navigateWithParams(mutate) {
    const params = new URLSearchParams(window.location.search);
    mutate(params);
    params.delete('page');
    window.location.assign(`${window.location.pathname}?${params.toString()}`);
}

/**
 * Fill in option lists and wire change handlers for the filter row.
 * @param {HTMLElement} container - the `.search-filter-row` element
 */
export function initSearchFilterBar(container) {
    const surface = currentSurface();
    const currentParams = new URLSearchParams(window.location.search);

    // Sticky-filter handoff: if the URL has no filter params, apply whatever
    // the modal/popovers last stored. Returns true when it triggered a
    // replace-navigation; bail out so we don't bind handlers on a page that's
    // about to unload.
    if (maybeApplyStickyFilters(surface, currentParams)) return;

    // URL is now the source of truth — mirror it into sessionStorage so the
    // modal sees the same filters next time it opens. Has to run *before* the
    // popovers are seeded so a stale sessionStorage doesn't leak into them.
    syncSessionStorageFromUrl(surface, currentParams);

    const availabilityEl = container.querySelector('ol-toggle');
    const languageEl = container.querySelector('ol-select-popover');

    // Build the facet field config now that we have element references.
    // Future filters: add an entry here.
    POPOVER_FIELD_CONFIG = new Map([
        ...(languageEl ? [[languageEl, 'language']] : []),
    ]);

    // True when the page has a meaningful search query — facet counts are only
    // fetched in this case. An empty or whitespace-only q= is treated as no
    // query (popularity-sorted catalogue, no per-query counts).
    const hasQuery = (currentParams.get('q') || '').trim().length > 0;

    if (availabilityEl) {
        availabilityEl.checked =
            surface.readAvailability(currentParams) !== DEFAULT_AVAILABILITY;
        availabilityEl.addEventListener('ol-toggle-change', (e) => {
            const value = e.detail.checked ? 'readable' : DEFAULT_AVAILABILITY;
            writeStoredAvailability(value);
            trackEvent('SearchFilter', e.detail.checked ? 'AvailabilityOn' : 'AvailabilityOff');
            const mapped = surface.availabilityParams(value);
            navigateWithParams((params) => {
                surface.availabilityParamKeys.forEach((key) => params.delete(key));
                Object.entries(mapped).forEach(([key, val]) => params.set(key, val));
            });
        });
    }

    if (languageEl) {
        // Seed with the curated defaults so a pre-selected language renders its
        // label immediately, without waiting on (or requiring) the network.
        languageEl.items = DEFAULT_LANGUAGE_OPTIONS;
        languageEl.selected = currentParams.getAll('language');

        // Defer fetching the full catalogue + context-aware counts until the
        // popover is first asked to open. On later opens of the same dropper
        // (same page load / same query) the counts are already merged into
        // `items`; nothing to re-fetch, and `load` below resolves immediately.
        let loaded = false;

        /**
         * Loads the catalogue + counts into languageEl.items. Passed to
         * openWhenCountsReady() as the work to race against the open budget,
         * so the panel opens once at its final size — no spinner-then-collapse
         * jump under the pointer, and no stale position from a mid-open resize.
         */
        async function loadLanguageItems() {
            if (loaded) return;
            loaded = true;

            const field = POPOVER_FIELD_CONFIG.get(languageEl);
            languageEl.loading = true;

            try {
                // fetchFacetCounts() strips any existing filter on `field`
                // itself before forwarding params — Solr ANDs an fq on the
                // field being counted, so leaving e.g. language=eng in would
                // zero out every other language. No manual stripping needed
                // here; pass currentParams straight through.
                const [options, counts] = await Promise.all([
                    fetchLanguageOptions(),
                    hasQuery && field && surface.facetCounts
                        ? fetchFacetCounts(field, currentParams)
                        : Promise.resolve([]),
                ]);

                languageEl.items = (hasQuery && counts.length > 0)
                    ? mergeFacetCounts(options, counts, languageEl.selected || [])
                    : options;
            } catch (err) {
                // Graceful degradation: keep DEFAULT_LANGUAGE_OPTIONS seeded at
                // init. Filtering must never break (spec requirement).
                // eslint-disable-next-line no-console
                console.warn('SearchFilterBar: facet counts fetch failed, falling back to uncounted list', err);
                // Allow a retry on the next open (e.g. flaky mobile network)
                // instead of leaving the popover permanently stuck on the
                // uncounted default list for the rest of the page's life.
                loaded = false;
            } finally {
                languageEl.loading = false;
            }
        }

        // Cancelable pre-open event: hold the panel shut, load, then show it
        // once (openWhenCountsReady handles the 500ms open budget + calling
        // popover.show()). Anything not listening for this event still opens
        // instantly, unaffected.
        languageEl.addEventListener('ol-select-popover-request-open', (e) => {
            openWhenCountsReady(e, loadLanguageItems);
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
