/**
 * Wires the availability toggle + language filter popover on any listing surface
 * that renders a `.search-filter-row` — the /search results page
 * (openlibrary/templates/work_search.html) and author pages
 * (type/author/view.html) today. They render empty from the template; this
 * module seeds them with the current selection, navigates the current page to an
 * updated URL when a filter changes, and keeps the durable reading preference
 * (availability + language) in localStorage so the header search modal, the
 * search-page filters, and other listing surfaces stay in sync.
 *
 * Persistence model — URL is the source of truth for the page:
 *
 *  - On init, if the URL carries any filter param (availability params or
 *    `language`), the stored preference is mirrored from the URL. This way the modal
 *    will reflect a filter change made via the toggle, the language popover, or
 *    the sidebar language facet (which navigates the page with a new `language=`
 *    param) the next time it opens.
 *
 *  - On init, if the URL carries NO filter params and the stored preference has
 *    a non-default value, we replace-navigate the current page with those sticky
 *    filters applied. This handles arriving from a search box submit on another
 *    page or from a bare URL — the user gets the filters they last set, including
 *    on a prior visit. The bar's own controls then render the inherited state
 *    visibly, which is what makes the cross-surface stickiness safe.
 *
 *  - The `filters=off` URL sentinel is a *scope-local* opt-out: a surface's
 *    "Show all" escape hatch uses it to show the full set on that page without
 *    inheriting OR clobbering the stored preference, so the global pref still
 *    applies elsewhere. Any explicit control change drops the sentinel.
 *
 * The full language catalogue is fetched lazily on first popover open.
 */

import {
    AVAILABILITY_TO_PARAMS,
    DEFAULT_AVAILABILITY,
    DEFAULT_LANGUAGE_OPTIONS,
    availabilityFromParams,
    readStoredAvailability,
    readStoredLanguages,
    writeStoredAvailability,
    writeStoredLanguages,
} from './search-modal/constants.js';
import { fetchLanguageOptions } from './search-modal/languages.js';
import { trackEvent } from './ol.analytics.js';

// Every query param the availability filter owns, across all of its values.
// Cleared before applying a new value so stale availability filters don't
// accumulate in the URL.
const AVAILABILITY_PARAM_KEYS = [
    ...new Set(Object.values(AVAILABILITY_TO_PARAMS).flatMap(Object.keys)),
];

// ── URL / sticky-filter helpers ────────────────────────────────────────────

function urlHasAnyFilterParam(params) {
    if (AVAILABILITY_PARAM_KEYS.some(k => params.has(k))) return true;
    if (params.has('language')) return true;
    return false;
}

/**
 * Mirror the current URL's filter state to the stored preference so the modal
 * (and other surfaces) open with the same selection next time. We always write
 * both keys so removing a filter via the popovers/sidebar clears the stored
 * value too.
 */
function syncStoredPrefFromUrl(params) {
    writeStoredAvailability(availabilityFromParams(name => params.get(name)));
    writeStoredLanguages(params.getAll('language'));
}

/**
 * If the URL has no filter params at all and the stored preference has a
 * non-default value, replace-navigate to the current page with the sticky
 * filters applied. Returns true when a navigation was kicked off (caller should
 * stop further init).
 *
 * The reading preference is global, so this inherits it onto whatever listing
 * page hosts the bar (/search, an author page, …) — the bar's own controls then
 * render the inherited state visibly, which is what makes the stickiness safe.
 *
 * `replace` is used so the unfiltered URL doesn't end up in the back-stack.
 */
function maybeApplyStickyFilters(params) {
    if (urlHasAnyFilterParam(params)) return false;

    const storedAvail = readStoredAvailability();
    const storedLangs = readStoredLanguages();
    if (storedAvail === DEFAULT_AVAILABILITY && storedLangs.length === 0) {
        return false;
    }

    const next = new URLSearchParams(params);
    const mapped = AVAILABILITY_TO_PARAMS[storedAvail] || {};
    Object.entries(mapped).forEach(([key, value]) => next.set(key, value));
    storedLangs.forEach(code => next.append('language', code));
    window.location.replace(`${window.location.pathname}?${next.toString()}`);
    return true;
}

/**
 * Navigate to the current page with its query string mutated by `mutate`.
 * Pagination is reset because the result set changes. Uses the live pathname so
 * the same bar drives /search and other listing surfaces (e.g. author pages).
 * @param {(params: URLSearchParams) => void} mutate
 */
function navigateWithParams(mutate) {
    const params = new URLSearchParams(window.location.search);
    mutate(params);
    params.delete('page');
    // An explicit filter change re-establishes intent, so drop any scope-local
    // `filters=off` sentinel — the resulting URL becomes the source of truth and
    // is mirrored back into the stored preference on the next load.
    params.delete('filters');
    window.location.assign(`${window.location.pathname}?${params.toString()}`);
}

/**
 * On narrow screens the availability + language controls collapse behind a
 * "Filters" button (`.search-filters__toggle`, rendered by
 * search/filters_disclosure). Wire it to expand/collapse the row and keep
 * `aria-expanded` in sync. On wide screens the button is `display: none` and
 * the row is always shown, so the listeners simply never fire — no-op there.
 * @param {HTMLElement} row - the `.search-filter-row` element
 */
function initFiltersDisclosure(row) {
    if (!row.id) return;
    const toggle = document.querySelector(`.search-filters__toggle[aria-controls="${row.id}"]`);
    if (!toggle) return;

    const setOpen = (open) => {
        row.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', String(open));
    };

    toggle.addEventListener('click', () => {
        setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });

    // Escape collapses the panel and returns focus to the trigger — but not when
    // it originated inside the language popover, which handles its own
    // Escape-to-close (its keydown bubbles up to this row too, and we'd otherwise
    // collapse the whole panel and steal focus on the same keypress).
    row.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        if (e.target.closest && e.target.closest('ol-select-popover')) return;
        setOpen(false);
        toggle.focus();
    });
}

/**
 * Fill in option lists and wire change handlers for the filter row.
 * @param {HTMLElement} container - the `.search-filter-row` element
 */
export function initSearchFilterBar(container) {
    const currentParams = new URLSearchParams(window.location.search);

    // Scope-local "Show all": a surface's empty/filtered-state escape hatch
    // navigates here with `filters=off` to mean "show the full set on THIS page
    // without changing my stored reading preference." Honor it by neither
    // inheriting the stored pref onto this URL nor mirroring this (deliberately
    // unfiltered) URL back over the stored pref — the global preference is left
    // intact so it still applies on /search and other listing surfaces. Any
    // explicit control change drops the sentinel (see navigateWithParams),
    // returning the page to normal URL-is-source-of-truth behavior.
    const scopeLocalUnfiltered = currentParams.get('filters') === 'off';

    // Sticky-filter handoff: if the URL has no filter params, apply whatever
    // the modal/popovers last stored. Returns true when it triggered a
    // replace-navigation; bail out so we don't bind handlers on a page that's
    // about to unload.
    if (!scopeLocalUnfiltered && maybeApplyStickyFilters(currentParams)) return;

    // URL is now the source of truth — mirror it into the stored preference so
    // the modal sees the same filters next time it opens. Has to run *before* the
    // popovers are seeded so a stale stored value doesn't leak into them. Skipped
    // under `filters=off` so a scope-local "Show all" doesn't clobber the pref.
    if (!scopeLocalUnfiltered) {
        syncStoredPrefFromUrl(currentParams);
    }

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
            trackEvent('SearchFilter', e.detail.checked ? 'AvailabilityOn' : 'AvailabilityOff');
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

    initFiltersDisclosure(container);
}
