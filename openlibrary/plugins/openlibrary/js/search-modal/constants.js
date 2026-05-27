/**
 * Filter options for the header search modal.
 */

export const AVAILABILITY_OPTIONS = [
    {
        value: 'all',
        label: 'All',
        description: 'Every book in the catalog',
    },
    {
        value: 'readable',
        label: 'Read now (free)',
        description: 'Fully readable – public domain & open access',
    },
    {
        value: 'borrowable',
        label: 'Borrowable',
        description: 'Borrow via Internet Archive\'s lending library',
    },
    {
        value: 'open',
        label: 'Preview only',
        description: 'Limited preview available',
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
    inputPlaceholder: 'Search books, authors…',
    inputAria: 'Search',
    scanAria: 'Scan a barcode',
    scanTitle: 'Scan barcode',
    closeAria: 'Close search',
    seeAll: 'See all results',
    activeFiltersAria: 'Active filters',
    removeFilter: 'Remove filter: %s',
    clearAll: 'Clear all',
    filtersAria: 'Search filters',
    availabilityLabel: 'Availability',
    languageLabel: 'Language',
    languagePlaceholder: 'Search languages…',
    languageHeading: 'Languages',
    startTyping: 'Start typing to search…',
    searching: 'Searching…',
    noResults: 'No results found',
    topResults: 'Top results',
    untitled: 'Untitled',
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
    readable: { public_scan: 'true' },
    borrowable: { has_fulltext: 'true', public_scan: 'false' },
    open: { print_disabled: 'true' },
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
