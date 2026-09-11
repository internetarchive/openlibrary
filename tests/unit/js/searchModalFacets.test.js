/**
 * Unit tests for the search modal's context-aware language counts.
 *
 * Exercises _loadLanguageFacets() directly on a SearchModal instance — the
 * merge itself is covered in searchFacets.test.js, so these cover the modal's
 * own concerns: when it fetches, when it doesn't, and what it shows on failure.
 *
 * Issue: #13060  —  feat(search): Wire facet droppers to context-aware counts
 */

import { fetchLanguageOptions } from '../../../openlibrary/plugins/openlibrary/js/search-modal/languages.js';
import { fetchFacetCounts } from '../../../openlibrary/plugins/openlibrary/js/search-modal/searchFacets.js';
import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';

jest.mock('../../../openlibrary/plugins/openlibrary/js/search-modal/languages.js');
jest.mock('../../../openlibrary/plugins/openlibrary/js/search-modal/searchFacets.js', () => ({
    ...jest.requireActual('../../../openlibrary/plugins/openlibrary/js/search-modal/searchFacets.js'),
    fetchFacetCounts: jest.fn(),
}));

const CATALOGUE = [
    { value: 'eng', label: 'English' },
    { value: 'ger', label: 'German'  },
    { value: 'fre', label: 'French'  },
];

const COUNTS = [
    { value: 'fre', label: 'French',  count: 12 },
    { value: 'eng', label: 'English', count: 4  },
];

/** A modal with a query typed in, its language catalogue already loaded. */
function makeModal(query = 'tolkien') {
    const modal = new SearchModal();
    modal._query = query;
    return modal;
}

beforeEach(() => {
    jest.clearAllMocks();
    fetchLanguageOptions.mockResolvedValue(CATALOGUE);
    fetchFacetCounts.mockResolvedValue(COUNTS);
});

describe('_loadLanguageFacets', () => {
    test('merges counts into the language items for the current query', async() => {
        const modal = makeModal();
        await modal._loadLanguageFacets();

        expect(fetchFacetCounts).toHaveBeenCalledTimes(1);
        expect(modal._languageItems).toEqual([
            { value: 'fre', label: 'French',  count: 12 },
            { value: 'eng', label: 'English', count: 4  },
        ]);
    });

    test('forwards the query and availability subset, but not the selection', async() => {
        const modal = makeModal();
        modal._availability = 'readable';
        modal._languages    = ['ger'];
        await modal._loadLanguageFacets();

        const [field, params] = fetchFacetCounts.mock.calls[0];
        expect(field).toBe('language');
        expect(params.get('q')).toBe('tolkien');
        expect(params.has('has_fulltext')).toBe(true);
        // Solr excludes a facet field from its own filter, so sending the
        // selection would only churn the cache key. See _buildFacetParams.
        expect(params.has('language')).toBe(false);
    });

    test('keeps a selected language visible even at zero count', async() => {
        const modal = makeModal();
        modal._languages = ['ger'];
        await modal._loadLanguageFacets();

        const german = modal._languageItems.find(it => it.value === 'ger');
        expect(german).toEqual({ value: 'ger', label: 'German', count: 0 });
    });

    test('does not fetch without a query, and drops a previous query\'s counts', async() => {
        const modal = makeModal();
        await modal._loadLanguageFacets();
        expect(modal._languageItems).toHaveLength(2);

        modal._query = '';
        await modal._loadLanguageFacets();

        expect(fetchFacetCounts).toHaveBeenCalledTimes(1);
        expect(modal._languageItems).toEqual(CATALOGUE);
    });

    test('re-opening on the same query does not refetch', async() => {
        const modal = makeModal();
        await modal._loadLanguageFacets();
        await modal._loadLanguageFacets();

        expect(fetchFacetCounts).toHaveBeenCalledTimes(1);
    });

    test('refetches when the query changes', async() => {
        const modal = makeModal();
        await modal._loadLanguageFacets();
        modal._query = 'asimov';
        await modal._loadLanguageFacets();

        expect(fetchFacetCounts).toHaveBeenCalledTimes(2);
    });

    test('refetches when the availability filter changes', async() => {
        const modal = makeModal();
        await modal._loadLanguageFacets();
        modal._availability = 'readable';
        await modal._loadLanguageFacets();

        expect(fetchFacetCounts).toHaveBeenCalledTimes(2);
    });

    test('falls back to the uncounted catalogue when the request fails', async() => {
        fetchFacetCounts.mockRejectedValue(new Error('HTTP 500'));
        const modal = makeModal();
        await modal._loadLanguageFacets();

        expect(modal._languageItems).toEqual(CATALOGUE);
        expect(modal._langsLoading).toBe(false);
    });

    test('retries after a failure instead of caching the empty result', async() => {
        fetchFacetCounts.mockRejectedValueOnce(new Error('HTTP 500'));
        const modal = makeModal();
        await modal._loadLanguageFacets();
        await modal._loadLanguageFacets();

        expect(fetchFacetCounts).toHaveBeenCalledTimes(2);
        expect(modal._languageItems).toHaveLength(2);
    });

    test('shows the uncounted catalogue when the query matches nothing', async() => {
        fetchFacetCounts.mockResolvedValue([]);
        const modal = makeModal();
        await modal._loadLanguageFacets();

        expect(modal._languageItems).toEqual(CATALOGUE);
    });

    test('clears the loading flag once counts land', async() => {
        const modal = makeModal();
        const pending = modal._loadLanguageFacets();
        expect(modal._langsLoading).toBe(true);
        await pending;
        expect(modal._langsLoading).toBe(false);
    });

    test('fetches the catalogue only once across repeated opens', async() => {
        const modal = makeModal();
        await modal._loadLanguageFacets();
        modal._query = 'asimov';
        await modal._loadLanguageFacets();

        expect(fetchLanguageOptions).toHaveBeenCalledTimes(1);
    });
});
