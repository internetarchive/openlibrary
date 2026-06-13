/**
 * Filter options for the header search modal.
 */

// Availability values and their display labels. The labels are the English
// source/fallback for the localized strings in search/availability_i18n.html;
// keep the two in sync. The header modal and the search-page filter row both
// surface availability as a binary "Readable Only" toggle, so only the
// `readable` label is rendered today; the full set mirrors the taxonomy in
// AVAILABILITY_TO_PARAMS and feeds availabilityFromParams' URL round-tripping.
export const AVAILABILITY_OPTIONS = [
    { value: 'all', label: 'All books' },
    { value: 'readable', label: 'Readable Only' },
    { value: 'open', label: 'Free to read now' },
    { value: 'borrowable', label: 'Borrow online' },
];

export const DEFAULT_AVAILABILITY = 'all';

/**
 * Returns a copy of AVAILABILITY_OPTIONS with each option's `label` replaced by
 * the translated string in `i18nStrings` (keyed by the option's `value`). The
 * English strings above are the source/fallback: any value the translations
 * omit keeps its built-in text, so a missing or partial translation never
 * blanks out an option.
 *
 * The translated strings are rendered server-side via search/availability_i18n
 * (Templetor `$_()`), since the JS-side `ugettext` is only a pass-through.
 *
 * @param {Object<string, {label?: string}>|null} i18nStrings
 * @returns {typeof AVAILABILITY_OPTIONS}
 */
export function localizeAvailabilityOptions(i18nStrings) {
    if (!i18nStrings) return AVAILABILITY_OPTIONS;
    return AVAILABILITY_OPTIONS.map((opt) => {
        const t = i18nStrings[opt.value];
        if (!t) return opt;
        return { ...opt, label: t.label || opt.label };
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
 * translation is present.
 */
export const DEFAULT_SEARCH_MODAL_STRINGS = {
    dialogAria: 'Search Open Library',
    inputPlaceholder: 'Search books and authors…',
    inputAria: 'Search',
    closeAria: 'Close search',
    clearAria: 'Clear search',
    seeAll: 'See all results',
    seeAllOne: 'See all %s result',
    seeAllMany: 'See all %s results',
    clearAll: 'Clear all',
    filtersAria: 'Search filters',
    availabilityLabel: 'Availability',
    languageLabel: 'Language',
    languagePlaceholder: 'Search languages…',
    languageHeading: 'Languages',
    searching: 'Searching…',
    noResults: 'No results found',
    // Screen-reader-only live announcement when results land: first %s = rows
    // shown in the modal, second %s = total matches. e.g. "Showing 7 of 134,731
    // results". Sighted users see the list appear; this gives assistive tech the
    // same feedback (see the aria-live region in SearchModal.render).
    resultsAnnounce: 'Showing %s of %s results',
    topResults: 'Top results',
    untitled: 'Untitled',
    authorLabel: 'Author',
    // Result-row access badge, shown for any readable book (public-domain or
    // lendable). Keep short — it sits in a small pill at the row edge.
    accessReadable: 'Readable',
    // Shown on a readable result whose only readable copy is in a language other
    // than the patron's site language. %s = the localized language name, e.g.
    // "In French". Filled client-side via sprintf.
    inLanguage: 'In %s',
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
 * The site's UI languages (2-letter codes from get_supported_languages, the
 * language switcher) → the MARC bibliographic code used by Solr's `language`
 * field. The site language a patron picks is one of these; the few MARC quirks
 * (cze, ger, fre, rum, chi) are deliberate — those are the bibliographic codes
 * Open Library indexes on (matching DEFAULT_LANGUAGE_OPTIONS), not the
 * terminology codes (ces/deu/fra/ron/zho). A self-contained map keeps the
 * comparison working without a per-render language-record lookup; an unmapped
 * code (e.g. a rare Accept-Language value) just yields no pill.
 */
export const UI_LANG_TO_MARC = {
    ar: 'ara',
    cs: 'cze',
    de: 'ger',
    en: 'eng',
    es: 'spa',
    fr: 'fre',
    hi: 'hin',
    hr: 'hrv',
    it: 'ita',
    pt: 'por',
    ro: 'rum',
    sc: 'srd',
    te: 'tel',
    uk: 'ukr',
    zh: 'chi',
    tl: 'tgl',
};

/**
 * Map a 2-letter UI language code to its MARC bibliographic code, or '' when it
 * isn't one of the known UI languages (the caller then suppresses the mismatch
 * pill rather than guessing).
 *
 * @param {string} iso
 * @returns {string}
 */
export function siteLanguageToMarc(iso) {
    return UI_LANG_TO_MARC[iso] || '';
}

/**
 * A MARC language code (e.g. 'fre') → its localized display name, looked up in
 * `options` (the modal's loaded catalogue) with DEFAULT_LANGUAGE_OPTIONS as the
 * pre-fetch fallback. Returns null for an unknown code so callers can skip
 * rather than surface a raw code.
 *
 * @param {Array<{value: string, label: string}>|null|undefined} options
 * @param {string} code
 * @returns {string|null}
 */
export function languageNameFromOptions(options, code) {
    const opts = options && options.length ? options : DEFAULT_LANGUAGE_OPTIONS;
    return opts.find((o) => o.value === code)?.label || null;
}

// Most languages to name in the "In <language>" hint before truncating to a
// trailing ", …". Two keeps the pill short while still signalling a multilingual
// readable copy (e.g. "In French, German, …").
const MISMATCH_LANG_LIMIT = 2;

/**
 * The localized language names to surface on a readable result whose promoted
 * edition is NOT in the patron's site language — or null when there's nothing to
 * flag. Used by the modal's "In <language>" hint so a patron isn't surprised by
 * the language of the copy a result opens. Shown on any row carrying the
 * "Readable" badge, independent of the Readable Only toggle (the caller gates on
 * the badge).
 *
 * Lists up to MISMATCH_LANG_LIMIT of the edition's languages, joined with ", ",
 * and appends a trailing ", …" when the edition carries more (e.g. "French,
 * German, …"). Unknown codes (no display name) are dropped before counting, so
 * they neither fill a slot nor force the ellipsis.
 *
 * Stays quiet (returns null) when: there's no promoted readable edition; the
 * patron already constrained the language; the site language is unknown; the
 * edition carries no language; the edition is already in the site language (this
 * also guarantees none of the named languages is the site language); or no code
 * resolves to a display name.
 *
 * @param {Object} args
 * @param {{language?: string[]}|null} args.edition - promoted readable edition
 * @param {string[]} args.languages - the patron's selected language filters
 * @param {string} args.siteLanguage - the patron's site language (MARC code)
 * @param {Array<{value: string, label: string}>|null} args.options - loaded language catalogue
 * @returns {string|null}
 */
export function readableLanguageMismatch({ edition, languages, siteLanguage, options }) {
    if (!edition) return null;                            // only promoted readable editions
    if (languages.length) return null;                   // patron already chose language(s)
    if (!siteLanguage) return null;                      // unknown site lang → don't guess
    const langs = edition.language;
    if (!Array.isArray(langs) || langs.length === 0) return null;
    if (langs.includes(siteLanguage)) return null;       // readable in their language → fine
    const names = langs
        .map((code) => languageNameFromOptions(options, code))
        .filter(Boolean);                                // drop codes with no display name
    if (names.length === 0) return null;
    const shown = names.slice(0, MISMATCH_LANG_LIMIT).join(', ');
    return names.length > MISMATCH_LANG_LIMIT ? `${shown}, …` : shown;
}

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
