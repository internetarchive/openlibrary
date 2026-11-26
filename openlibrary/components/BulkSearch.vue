<template>
    <div class="ol-bulk-search">
        <BulkSearchControls :bulk-search-state="bulkSearchState" />
        <hr />
        <MatchTable v-if="bulkSearchState.matchedBooks.length" :bulk-search-state="bulkSearchState" :list-url="bulkSearchState.listUrl" />
    </div>
</template>

<script>
import BulkSearchControls from './BulkSearch/components/BulkSearchControls.vue';
import { BulkSearchState } from './BulkSearch/utils/classes.js';
import MatchTable from './BulkSearch/components/MatchTable.vue';

/**
 * English fallbacks for the translated strings passed in from the server,
 * bulk_search_strings() in plugins/worksearch/bulk_search.py; test_bulk_search_page.py
 * checks they match. `editions` is a plural set, keyed by CLDR plural category.
 */
const DEFAULT_STRINGS = {
    columnHint: 'Please include a header row. Supported columns include: "Title", "Author", "ISBN".',
    enterBooks: 'Enter your books below.',
    enterBooksHint: 'One per line, or paste from a spreadsheet.',
    trySample: 'Try a Sample...',
    sample1927: '1927 Books',
    samplePublicDomain2023: '2023 Public Domain Day',
    sampleHolocaust: 'Holocaust Wikipedia citations',
    inputPlaceholder: 'Enter your books...',
    extractBooks: 'Extract Books',
    extractDescription: 'How to convert your books above into structured information, like title and author.',
    extractor: 'Extractor',
    apiKey: 'OpenAI API Key',
    apiKeyPlaceholder: 'OpenAI API key here....',
    loading: 'Loading...',
    matchBooks: 'Match Books',
    matchDescription: "Once structured data has been found, it's time to match it to a book in OpenLibrary!",
    options: 'Options',
    useAuthor: 'Use author in search query',
    saveMatches: 'Save your Matches',
    saveDescription: "Now that you've found your books, why not save them to your reading log? Or a list?",
    addToList: 'Add to list',
    patternTitleByAuthor: 'Pattern: Title by Author',
    patternAuthorTitle: 'Pattern: Author - Title',
    patternTitleAuthor: 'Pattern: Title - Author',
    patternTitleParenAuthor: 'Pattern: Title (Author)',
    patternWikipedia: 'Wikipedia Citation Pattern: (e.g. Baum, Frank L. (1994). The Wizard of Oz)',
    aiExtraction: '✨ AI Extraction (Beta)',
    tableExtraction: 'Extract from a Table/Spreadsheet',
    extractedBooks: 'Extracted Books',
    matchedBooks: 'Matched Books',
    title: 'Title',
    author: 'Author',
    isbn: 'ISBN',
    viewResults: 'View results in Open Library',
    noBooksFound: 'No Books Found',
    editions: { one: '%(count)s edition', other: '%(count)s editions' }
};

export default {
    components: {
        BulkSearchControls,
        MatchTable
    },
    provide() {
        return { strings: this.strings };
    },
    props: {
        /** URI-encoded JSON of translated strings. */
        i18n: {
            type: String,
            default: ''
        }
    },
    data() {
        let strings = DEFAULT_STRINGS;
        try {
            strings = { ...DEFAULT_STRINGS, ...JSON.parse(decodeURIComponent(this.i18n)) };
        } catch {
            // A missing or malformed translation payload falls back to English.
        }
        return {
            strings,
            bulkSearchState: new BulkSearchState(strings)
        };
    }
};
</script>

<style>
.ol-bulk-search {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji';
}

button,
select,
input {
    font-family: inherit;
}
button,
textarea {
    font-size: inherit;
}
select,
input,
textarea {
    padding: 6px;
}
</style>
