/**
 * Translated UI strings for the Bulk Search page.
 *
 * Bulk Search renders in the browser, so `$_()` cannot reach these strings.
 * The page template (openlibrary/templates/bulk_search/bulk_search.html.jinja)
 * builds this payload server-side and URL-encodes it onto the <ol-bulk-search>
 * element's `i18n` attribute; BulkSearch.vue merges it over the defaults below.
 * A key the locale has not translated keeps its English text.
 */

import { fmt, plural } from '../../lit/utils/labels.js';

export const DEFAULT_BULK_SEARCH_STRINGS = {
    // Controls
    columnHint: 'Please include a header row. Supported columns include: "Title", "Author", "ISBN".',
    instructions: 'Enter your books below - one per line, or paste from a spreadsheet.',
    inputPlaceholder: 'Enter your books...',
    trySample: 'Try a Sample...',
    extractHeading: 'Extract Books',
    extractDescription: 'How to convert your books above into structured information, like title and author.',
    extractorLabel: 'Extractor',
    apiKeyLabel: 'OpenAI API Key',
    apiKeyPlaceholder: 'OpenAI API key here....',
    extractButton: 'Extract Books',
    loading: 'Loading...',
    matchHeading: 'Match Books',
    matchDescription: "Once structured data has been found, it's time to match it to a book in OpenLibrary!",
    optionsLabel: 'Options',
    useAuthor: 'Use author in search query',
    matchButton: 'Match Books',
    saveHeading: 'Save your Matches',
    saveDescription: "Now that you've found your books, why not save them to your reading log? Or a list?",
    addToList: 'Add to list',
    addToListSubmit: 'Add to List',
    // Results table
    extractedBooks: 'Extracted Books',
    matchedBooks: 'Matched Books',
    viewResults: 'View results in Open Library',
    noBooksFound: 'No Books Found',
    editions: { one: '%(count)s edition', other: '%(count)s editions' },
    // Extraction patterns
    extractorPatternTitleByAuthor: 'Pattern: Title by Author',
    extractorPatternAuthorTitle: 'Pattern: Author - Title',
    extractorPatternTitleAuthor: 'Pattern: Title - Author',
    extractorPatternTitleAuthorParens: 'Pattern: Title (Author)',
    extractorWikipediaCitation: 'Wikipedia Citation Pattern: (e.g. Baum, Frank L. (1994). The Wizard of Oz)',
    extractorAi: '✨ AI Extraction (Beta)',
    extractorTable: 'Extract from a Table/Spreadsheet'
};

/**
 * Decode the URL-encoded JSON the page puts in the `i18n` attribute and merge
 * it over the English defaults. A missing, malformed or
 * non-object payload falls back to English rather than throwing, so one bad
 * attribute cannot take down the page.
 *
 * @param {string|undefined|null} raw
 * @returns {typeof DEFAULT_BULK_SEARCH_STRINGS}
 */
export function bulkSearchStringsFromAttr(raw) {
    let overrides = null;
    try {
        if (raw) overrides = JSON.parse(decodeURIComponent(raw));
    } catch {
        /* fall back to the English defaults below */
    }
    if (!overrides || typeof overrides !== 'object' || Array.isArray(overrides)) {
        return DEFAULT_BULK_SEARCH_STRINGS;
    }
    return { ...DEFAULT_BULK_SEARCH_STRINGS, ...overrides };
}

/**
 * Resolve one string. A plural set (keyed by CLDR category) is narrowed by
 * `vars.count`; `%(name)s` placeholders are then filled from `vars`.
 *
 * @param {Object<string, any>} strings
 * @param {string} key
 * @param {Object<string, any>} [vars]
 * @returns {string}
 */
export function bulkSearchString(strings, key, vars) {
    const value = strings?.[key] ?? DEFAULT_BULK_SEARCH_STRINGS[key] ?? key;
    if (typeof value !== 'string') {
        return fmt(plural(value, vars?.count ?? 0), vars ?? { count: 0 });
    }
    return vars ? fmt(value, vars) : value;
}
