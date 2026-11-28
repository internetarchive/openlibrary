/**
 * Filter options for the header search modal.
 */
import { _ } from '../i18n.js';

// Availability values and their display labels. The header modal and the
// search-page filter row both surface availability as a binary "Readable Only"
// toggle, so only the `readable` label is rendered today; the full set mirrors
// the taxonomy in AVAILABILITY_TO_PARAMS and feeds availabilityFromParams' URL
// round-tripping. `value` is an identifier, never translated.
export const AVAILABILITY_OPTIONS = [
    { value: 'all', label: _('All books') },
    { value: 'readable', label: _('Readable Only') },
    { value: 'open', label: _('Free to read now') },
    { value: 'borrowable', label: _('Borrow online') }
];

export const DEFAULT_AVAILABILITY = 'all';

/**
 * The header search modal's chrome strings (labels, placeholders, aria-labels,
 * status messages), in the page language. `%s` placeholders are filled with sprintf.
 */
export const DEFAULT_SEARCH_MODAL_STRINGS = {
    dialogAria: _('Search Open Library'),
    inputPlaceholder: _('Search books and authors…'),
    inputAria: _('Search'),
    closeAria: _('Close search'),
    clearAria: _('Clear search'),
    // Footer button label. "all" only appears when there are more matches than
    // the modal renders inline — when every hit is already shown there's nothing
    // more to "see all" of. seeOne/seeMany are the all-shown cases; seeAllMany is
    // the there's-more case (always plural, since a lone result is always shown).
    // Counts are books (works); author rows come from the same docs.
    seeAll: _('See results'),
    // Zero hits: the button still leads to /search, so name the destination.
    seeNone: _('Go to full search'),
    seeOne: _('See %s book'),
    seeMany: _('See %s books'),
    seeAllMany: _('See all %s books'),
    // Narrow-footer form of seeAllMany; the wide form stays the accessible name.
    seeAllManyNarrow: _('All %s books'),
    clearAll: _('Clear all'),
    // Scope tabs: the catalogue, and the text of the scans.
    tabsAria: _('Search scope'),
    tabBooks: _('Books'),
    tabInside: _('Inside books'),
    filtersAria: _('Search filters'),
    availabilityLabel: _('Availability'),
    languageLabel: _('Language'),
    languagePlaceholder: _('Search languages…'),
    languageHeading: _('Languages'),
    // Loading labels, one per scope tab so the wait names what's being searched.
    searchingBooks: _('Searching books and authors…'),
    searchingInside: _('Searching inside books…'),
    noResults: _('No results found'),
    // When only the Search Inside band has matches, "No results found" would contradict it.
    noCatalogResults: _('No matching books or authors'),
    // Screen-reader-only live announcement when results land: %(shown)s = rows
    // shown in the modal, %(total)s = total matches. e.g. "Showing 7 of 134,731
    // results". Sighted users see the list appear; this gives assistive tech the
    // same feedback (see the aria-live region in SearchModal.render).
    resultsAnnounce: _('Showing %(shown)s of %(total)s results'),
    authorResults: _('Authors'),
    topResults: _('Books'),
    untitled: _('Untitled'),
    authorLabel: _('Author'),
    // Result-row access badge, shown beside the title for any readable book
    // (public-domain or lendable). Keep short — it sits in a small badge.
    accessReadable: _('Readable'),
    // Replaces "Readable" when the readable copy is in a language other than the
    // patron's site language. %s = the localized language name, e.g.
    // "Readable in French". Filled client-side via sprintf.
    readableInLanguage: _('Readable in %s'),
    recentSearches: _('Recent searches'),
    removeRecent: _('Remove "%s" from recent searches'),
    insideHeading: _('Search inside books'),
    // Inside tab footer action. %s = books with matches.
    seeAllInsideOne: _('Search Inside %s book'),
    seeAllInsideMany: _('Search Inside %s books'),
    // Before a total is measured for the current input.
    seeAllInsidePlain: _('Search Inside'),
    // Crosses from the band to the Inside books tab — it doesn't leave the modal.
    viewAllInside: _('View all'),
    // Inside tab placeholder, too-short prompt, and empty result.
    insidePlaceholder: _('Search inside books…'),
    insidePrompt: _('Type a word or phrase to find it on the pages of millions of books.'),
    noInsideResults: _('No matches inside books'),
    // Replaces the empty state when the fulltext backend failed, so an outage
    // doesn't read as a verdict on the query.
    insideError: _('Search inside books is temporarily unavailable. Please try again later.'),
    // Above Inside tab hits when the query was searched as one exact phrase. %s = the query.
    insideExactMatches: _('Showing exact matches for "%s".'),
    // Follows insideExactMatches; reruns the query as loose words.
    insideSearchAllWords: _('Search for all of these words instead.'),
    // Above Inside tab hits after the patron chose all words.
    insideAllWords: _('Showing all of these words, in any order.'),
    // Follows insideAllWords; goes back to the exact phrase.
    insideSearchExactPhrase: _('Search for the exact phrase instead.'),
    // The exact phrase found nothing, so the hits match all the words. %s = the query.
    insideNoExactMatches: _('No exact matches for "%s". Showing books containing all of these words.'),
    // %s = snippet rows shown (1–3), not the backend total.
    insideAnnounceOne: _('%s match found inside books'),
    insideAnnounceMany: _('%s matches found inside books')
};

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
    open: { public_scan: 'true' }
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
    const matches = params => Object.entries(params).every(([k, v]) => String(get(k) ?? '') === v);
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
    { value: 'ben', label: 'Bengali' }
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
    tl: 'tgl'
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
    return opts.find(o => o.value === code)?.label || null;
}

// Most languages to name in the "In <language>" hint before truncating to a
// trailing ", …". Two keeps the pill short while still signalling a multilingual
// readable copy (e.g. "In French, German, …").
const HINT_LANG_LIMIT = 2;

/**
 * Format an edition's language codes as a short, localized list for the
 * "In <language>" hint: up to HINT_LANG_LIMIT names joined with ", ", with a
 * trailing ", …" when more remain. Codes with no display name are dropped before
 * counting, so they neither fill a slot nor force the ellipsis. Returns null when
 * the edition carries no language or none of its codes resolve to a name.
 *
 * @param {string[]|undefined} langs - the edition's MARC language codes
 * @param {Array<{value: string, label: string}>|null} options - loaded catalogue
 * @returns {string|null}
 */
function listEditionLanguages(langs, options) {
    if (!Array.isArray(langs) || langs.length === 0) return null;
    const names = langs.map(code => languageNameFromOptions(options, code)).filter(Boolean); // drop codes with no display name
    if (names.length === 0) return null;
    const shown = names.slice(0, HINT_LANG_LIMIT).join(', ');
    return names.length > HINT_LANG_LIMIT ? `${shown}, …` : shown;
}

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
 * The "patron already chose a language" case is handled differently when they
 * pick *several* languages — see readableEditionLanguages, which then names the
 * copy's language so the patron can tell which of their filters a row satisfies.
 *
 * @param {Object} args
 * @param {{language?: string[]}|null} args.edition - promoted readable edition
 * @param {string[]} args.languages - the patron's selected language filters
 * @param {string} args.siteLanguage - the patron's site language (MARC code)
 * @param {Array<{value: string, label: string}>|null} args.options - loaded language catalogue
 * @returns {string|null}
 */
export function readableLanguageMismatch({ edition, languages, siteLanguage, options }) {
    if (!edition) return null; // only promoted readable editions
    if (languages.length) return null; // patron already chose language(s)
    if (!siteLanguage) return null; // unknown site lang → don't guess
    const langs = edition.language;
    if (!Array.isArray(langs) || langs.length === 0) return null;
    if (langs.includes(siteLanguage)) return null; // readable in their language → fine
    return listEditionLanguages(langs, options);
}

/**
 * The localized language name(s) to surface on a readable result when the patron
 * has filtered by MORE THAN ONE language. With several languages selected, any
 * given readable copy could be in any of them, so naming the promoted edition's
 * language tells the patron which of their filters this row satisfies — the
 * complement to readableLanguageMismatch's no-filter case.
 *
 * Stays quiet (returns null) when there's no promoted readable edition, fewer
 * than two languages are selected (a single filter constrains every result to it,
 * so naming it is redundant), the edition carries no language, or none of its
 * codes resolve to a display name. The site language is irrelevant here — the
 * patron's explicit language choice overrides it.
 *
 * @param {Object} args
 * @param {{language?: string[]}|null} args.edition - promoted readable edition
 * @param {string[]} args.languages - the patron's selected language filters
 * @param {Array<{value: string, label: string}>|null} args.options - loaded language catalogue
 * @returns {string|null}
 */
export function readableEditionLanguages({ edition, languages, options }) {
    if (!edition) return null; // only promoted readable editions
    if (!languages || languages.length < 2) return null; // only when juggling several filters
    return listEditionLanguages(edition.language, options);
}

/**
 * sessionStorage keys for per-session filter persistence.
 */
export const SS_AVAILABILITY_KEY = 'ol-header-search-availability';
export const SS_LANGUAGES_KEY = 'ol-header-search-languages';

/**
 * sessionStorage read/write that swallow access errors (private browsing, quota,
 * disabled storage). `ssGet` returns null on failure; `ssSet` is a no-op. Shared
 * by the header modal and the search-page filter row so both persist filter
 * state the same way.
 *
 * @param {string} key
 * @returns {string|null}
 */
export function ssGet(key) {
    try {
        return sessionStorage.getItem(key);
    } catch {
        return null;
    }
}

/**
 * @param {string} key
 * @param {string} value
 */
export function ssSet(key, value) {
    try {
        sessionStorage.setItem(key, value);
    } catch {
        /* ignore */
    }
}

/**
 * localStorage key and cap for per-device recent searches.
 */
export const LS_RECENT_SEARCHES_KEY = 'ol-recent-searches';
export const RECENT_SEARCHES_MAX = 8;

/** Every stored entry as {q, mode, allWords?}. Entries saved before modes were recorded are Books searches. */
function readRecentEntries() {
    try {
        const raw = localStorage.getItem(LS_RECENT_SEARCHES_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed
            .map(entry => (typeof entry === 'string' ? { q: entry, mode: 'books' } : entry))
            .filter(entry => entry && typeof entry.q === 'string' && typeof entry.mode === 'string');
    } catch {
        return [];
    }
}

/**
 * The recent searches made on one tab, newest first. Returns [] on any failure.
 * Non-string entries (from a corrupt or hand-edited value) are dropped so
 * callers only ever see strings to render and dedup against.
 * @param {string} mode - 'books' or 'inside'
 * @returns {string[]}
 */
export function readRecentSearches(mode = 'books') {
    return readRecentEntries()
        .filter(entry => entry.mode === mode)
        .map(entry => entry.q)
        .slice(0, RECENT_SEARCHES_MAX);
}

/**
 * Prepend `query` to the tab's recent searches, dedup, and cap that tab's list
 * at RECENT_SEARCHES_MAX. Silently ignores localStorage errors (private browsing).
 * @param {string} query
 * @param {string} mode
 * @param {{allWords?: boolean}} [options] - allWords: the patron chose all words over the exact phrase
 */
export function saveRecentSearch(query, mode = 'books', { allWords = false } = {}) {
    const trimmed = query.trim();
    if (!trimmed) return;
    try {
        const others = readRecentEntries().filter(entry => entry.mode !== mode);
        const own = readRecentEntries().filter(entry => entry.mode === mode && entry.q !== trimmed);
        own.unshift({ q: trimmed, mode, ...(allWords ? { allWords: true } : {}) });
        localStorage.setItem(LS_RECENT_SEARCHES_KEY, JSON.stringify([...own.slice(0, RECENT_SEARCHES_MAX), ...others]));
    } catch {
        /* ignore */
    }
}

/**
 * Whether a recent search was last run as all words rather than the exact phrase.
 * @param {string} query
 * @param {string} mode
 * @returns {boolean}
 */
export function recentSearchUsedAllWords(query, mode = 'books') {
    return readRecentEntries().some(entry => entry.mode === mode && entry.q === query && entry.allWords === true);
}

/**
 * Remove a single entry from one tab's recent searches.
 * @param {string} query
 * @param {string} mode
 * @returns {string[]} that tab's updated list
 */
export function removeRecentSearch(query, mode = 'books') {
    try {
        const entries = readRecentEntries().filter(entry => !(entry.mode === mode && entry.q === query));
        localStorage.setItem(LS_RECENT_SEARCHES_KEY, JSON.stringify(entries));
    } catch {
        /* ignore */
    }
    return readRecentSearches(mode);
}

/**
 * Read the language list from sessionStorage. Guards against missing values,
 * unparsable JSON, and values that parse to a non-array (e.g. a previously
 * stored object or string), any of which would otherwise leave callers with a
 * non-iterable or character-iterable value. Non-string entries are dropped so a
 * corrupt value can't surface as a bogus `language=<n>` filter.
 *
 * @returns {string[]}
 */
export function readStoredLanguages() {
    const raw = ssGet(SS_LANGUAGES_KEY);
    if (!raw) return [];
    try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed.filter(s => typeof s === 'string') : [];
    } catch {
        return [];
    }
}
