/**
 * Filter options for the header search modal.
 */

// Counts are rounded from production openlibrary.org facets (NOT fetched live)
// — they give the user a sense of scale without an extra round-trip and stay
// stable across renders. Last verified 2026-06-02: all=23.2M, readable=4.62M
// (public+borrowable), open/public=1.86M, borrowable=2.75M. The nested counts
// sum to their parent exactly (1.86M + 2.75M = 4.62M); print-disabled-only
// scans are excluded from `has_fulltext` for non-print-disabled patrons. Bump
// these when the corpus shifts materially.
// `nested: true` marks an option as a subset of the broader option above it
// ("Readable Only"), so the filter indents it and marks it in-scope when the
// parent is selected. `icon` names a glyph in OlAvailabilityFilter._icons.
export const AVAILABILITY_OPTIONS = [
    {
        value: 'all',
        label: 'All books',
        description: 'Including print-only books with no digital copy',
        count: '23M',
        icon: 'book',
    },
    {
        value: 'readable',
        label: 'Readable Only',
        description: 'Anything you can read in your browser',
        count: '4.6M',
        icon: 'globe',
    },
    {
        value: 'open',
        label: 'Free to read now',
        description: 'Public domain & openly licensed',
        count: '1.9M',
        nested: true,
        icon: 'unlock',
    },
    {
        value: 'borrowable',
        label: 'Borrow online',
        description: 'Digital loan - one reader at a time, may have a waitlist',
        count: '2.8M',
        nested: true,
        icon: 'clock',
    },
];

export const DEFAULT_AVAILABILITY = 'all';

/**
 * Returns a copy of AVAILABILITY_OPTIONS with each option's `label` and
 * `description` replaced by the translated strings in `i18nStrings` (keyed by
 * the option's `value`). The English strings above are the source/fallback:
 * any value the translations omit keeps its built-in text, so a missing or
 * partial translation never blanks out an option.
 *
 * The translated strings are rendered server-side via search/availability_i18n
 * (Templetor `$_()`), since the JS-side `ugettext` is only a pass-through.
 *
 * @param {Object<string, {label?: string, description?: string}>|null} i18nStrings
 * @returns {typeof AVAILABILITY_OPTIONS}
 */
export function localizeAvailabilityOptions(i18nStrings) {
    if (!i18nStrings) return AVAILABILITY_OPTIONS;
    return AVAILABILITY_OPTIONS.map((opt) => {
        const t = i18nStrings[opt.value];
        if (!t) return opt;
        return {
            ...opt,
            label: t.label || opt.label,
            description: t.description || opt.description,
        };
    });
}

/**
 * Reads translated availability strings from an element's `data-i18n` JSON
 * attribute (rendered by search/availability_i18n.html) and returns the
 * localized option list. Falls back to the English defaults when the attribute
 * is absent or malformed.
 *
 * @param {Element|null} el
 * @returns {typeof AVAILABILITY_OPTIONS}
 */
export function availabilityOptionsFromElement(el) {
    let i18nStrings = null;
    try {
        const raw = el && el.dataset ? el.dataset.i18n : null;
        if (raw) i18nStrings = JSON.parse(raw);
    } catch { /* fall back to the English defaults below */ }
    return localizeAvailabilityOptions(i18nStrings);
}

/**
 * English source/fallback for the header search modal's chrome strings (labels,
 * placeholders, aria-labels, status messages). Rendered server-side by
 * search/search_modal_i18n.html via `$_()`; this object is what ships when no
 * translation is present. `%s` in `removeFilter` is filled in at runtime with
 * the filter label (see SearchModal._renderChips).
 */
export const DEFAULT_SEARCH_MODAL_STRINGS = {
    dialogAria: 'Search Open Library',
    inputPlaceholder: 'Search books and authors…',
    inputAria: 'Search',
    closeAria: 'Close search',
    seeAll: 'See all results',
    seeAllOne: 'See all %s result',
    seeAllMany: 'See all %s results',
    activeFiltersAria: 'Active filters',
    removeFilter: 'Remove filter: %s',
    clearAll: 'Clear all',
    filtersAria: 'Search filters',
    availabilityLabel: 'Availability',
    languageLabel: 'Language',
    languagePlaceholder: 'Search languages…',
    languageHeading: 'Languages',
    searching: 'Searching…',
    noResults: 'No results found',
    topResults: 'Top results',
    untitled: 'Untitled',
    authorLabel: 'Author',
    recentSearches: 'Recent searches',
    removeRecent: 'Remove "%s" from recent searches',
};

/**
 * Reads translated modal chrome strings from an element's `data-i18n-ui` JSON
 * attribute (rendered by search/search_modal_i18n.html) and merges them over
 * DEFAULT_SEARCH_MODAL_STRINGS, so any key the translations omit keeps its
 * English text. Falls back to the full English set when the attribute is absent
 * or malformed.
 *
 * @param {Element|null} el
 * @returns {typeof DEFAULT_SEARCH_MODAL_STRINGS}
 */
export function searchModalStringsFromElement(el) {
    let overrides = null;
    try {
        const raw = el && el.dataset ? el.dataset.i18nUi : null;
        if (raw) overrides = JSON.parse(raw);
    } catch { /* fall back to the English defaults below */ }
    return overrides
        ? { ...DEFAULT_SEARCH_MODAL_STRINGS, ...overrides }
        : DEFAULT_SEARCH_MODAL_STRINGS;
}

/**
 * Maps an availability value to the `/search` query params that express it.
 * Shared by the header modal and the search-page filter row so both produce
 * identical filters. The param names match WorkSearchScheme.facet_rewrites
 * (`public_scan`, `print_disabled`, `has_fulltext`).
 */
export const AVAILABILITY_TO_PARAMS = {
    all: {},
    // "Readable Only" — everything a patron can read without special access:
    // ebook_access:[borrowable TO *] via has_fulltext (public + borrowable).
    readable: { has_fulltext: 'true' },
    // "Borrow online" — readable but not public: borrowable scans only.
    borrowable: { has_fulltext: 'true', public_scan: 'false' },
    // "Free to read now" — public-domain / open-access scans (ebook_access:public).
    open: { public_scan: 'true' },
};

/**
 * Inverse of AVAILABILITY_TO_PARAMS: given a param lookup (a function or object
 * returning the current value of a param name), returns the matching
 * availability value. Falls back to DEFAULT_AVAILABILITY when nothing matches.
 *
 * @param {(name: string) => string|null|undefined} get - param accessor
 * @returns {string}
 */
export function availabilityFromParams(get) {
    const matches = (params) =>
        Object.entries(params).every(([k, v]) => String(get(k) ?? '') === v);
    // Check specific (multi-param) values before less specific ones; skip `all`
    // (the empty default) so it only wins when nothing else matches.
    for (const value of ['borrowable', 'readable', 'open']) {
        if (matches(AVAILABILITY_TO_PARAMS[value])) return value;
    }
    return DEFAULT_AVAILABILITY;
}

/**
 * The 20 default languages shown immediately when the Language popover
 * opens (before any API response arrives, or if the fetch fails).
 *
 * Chosen by OL catalogue volume – the languages most likely to be useful
 * to a patron on the first click. Sorted by global speaker population /
 * OL catalog representation.
 *
 * fetchLanguageOptions() (languages.js) fetches the full OL language
 * catalogue from /languages.json – translated names, volume-ranked – and
 * replaces this list so every language in the catalogue becomes searchable.
 * This array is the instant-render and fetch-failure fallback only.
 */
export const DEFAULT_LANGUAGE_OPTIONS = [
    { value: 'eng', label: 'English' },
    { value: 'fre', label: 'French' },
    { value: 'ger', label: 'German' },
    { value: 'spa', label: 'Spanish' },
    { value: 'por', label: 'Portuguese' },
    { value: 'ita', label: 'Italian' },
    { value: 'rus', label: 'Russian' },
    { value: 'chi', label: 'Chinese' },
    { value: 'jpn', label: 'Japanese' },
    { value: 'ara', label: 'Arabic' },
    { value: 'dut', label: 'Dutch' },
    { value: 'pol', label: 'Polish' },
    { value: 'swe', label: 'Swedish' },
    { value: 'tur', label: 'Turkish' },
    { value: 'hin', label: 'Hindi' },
    { value: 'kor', label: 'Korean' },
    { value: 'lat', label: 'Latin' },
    { value: 'per', label: 'Persian' },
    { value: 'heb', label: 'Hebrew' },
    { value: 'ben', label: 'Bengali' },
];

/**
 * sessionStorage keys for per-session filter persistence.
 */
export const SS_AVAILABILITY_KEY = 'ol-header-search-availability';
export const SS_LANGUAGES_KEY    = 'ol-header-search-languages';

/**
 * localStorage key and cap for per-device recent searches.
 */
export const LS_RECENT_SEARCHES_KEY = 'ol-recent-searches';
export const RECENT_SEARCHES_MAX    = 8;

/**
 * Read the recent-search list from localStorage. Returns [] on any failure.
 * @returns {string[]}
 */
export function readRecentSearches() {
    try {
        const raw = localStorage.getItem(LS_RECENT_SEARCHES_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed.slice(0, RECENT_SEARCHES_MAX) : [];
    } catch { return []; }
}

/**
 * Prepend `query` to the recent-search list, dedup, and cap at
 * RECENT_SEARCHES_MAX. Silently ignores localStorage errors (private browsing).
 * @param {string} query
 */
export function saveRecentSearch(query) {
    const trimmed = query.trim();
    if (!trimmed) return;
    try {
        const searches = readRecentSearches().filter(s => s !== trimmed);
        searches.unshift(trimmed);
        localStorage.setItem(
            LS_RECENT_SEARCHES_KEY,
            JSON.stringify(searches.slice(0, RECENT_SEARCHES_MAX))
        );
    } catch { /* ignore */ }
}

/**
 * Remove a single entry from the recent-search list.
 * @param {string} query
 * @returns {string[]} updated list
 */
export function removeRecentSearch(query) {
    try {
        const searches = readRecentSearches().filter(s => s !== query);
        localStorage.setItem(LS_RECENT_SEARCHES_KEY, JSON.stringify(searches));
        return searches;
    } catch { return readRecentSearches(); }
}

/**
 * Read the language list from sessionStorage. Guards against missing values,
 * unparseable JSON, and values that parse to a non-array (e.g. a previously
 * stored object or string), any of which would otherwise leave callers with a
 * non-iterable or character-iterable value.
 *
 * @returns {string[]}
 */
export function readStoredLanguages() {
    let raw = null;
    try { raw = sessionStorage.getItem(SS_LANGUAGES_KEY); } catch { return []; }
    if (!raw) return [];
    try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
}
