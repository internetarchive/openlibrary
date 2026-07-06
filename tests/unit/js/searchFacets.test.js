/**
 * Unit tests for:
 *   - fetchFacetCounts()  (searchFacets.js)
 *   - mergeFacetCounts()  (SearchFilterBar.js)
 *
 * Run with: jest (or vitest — both work without config changes)
 *
 * Issue: #13060  —  feat(search): Wire facet droppers to context-aware counts
 */

import { fetchFacetCounts } from '../../../openlibrary/plugins/openlibrary/js/search-modal/searchFacets.js';
import { mergeFacetCounts } from '../../../openlibrary/plugins/openlibrary/js/SearchFilterBar.js';
// ─────────────────────────────────────────────────────────────────────────────
// fetchFacetCounts
// ─────────────────────────────────────────────────────────────────────────────

describe('fetchFacetCounts', () => {
    const MOCK_FLAT = [
        { value: 'English', count: 665 },
        { value: 'German',  count: 32  },
        { value: 'Spanish', count: 18  },
    ];

    beforeEach(() => {
        jest.resetAllMocks();
    });

    test('calls /search/facets.json with field + forwarded search params', async() => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async() => MOCK_FLAT,
        });

        const params = new URLSearchParams('q=lord+of+the+rings&sort=new');
        await fetchFacetCounts('language', params);

        const url = global.fetch.mock.calls[0][0];
        expect(url).toContain('/search/facets.json');
        expect(url).toContain('field=language');
        expect(url).toContain('q=lord+of+the+rings');
    });

    test('returns a flat array when the API responds with a flat array', async() => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async() => MOCK_FLAT,
        });

        const result = await fetchFacetCounts('language', new URLSearchParams('q=foo'));
        expect(result).toEqual(MOCK_FLAT);
    });

    test('unwraps a field-keyed map when the API responds with the multi-field shape', async() => {
        const multiShape = { language: MOCK_FLAT, author_facet: [] };
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async() => multiShape,
        });

        const result = await fetchFacetCounts('language', new URLSearchParams('q=foo'));
        expect(result).toEqual(MOCK_FLAT);
    });

    test('returns [] when a field-keyed map does not contain the requested field', async() => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async() => ({ author_facet: [{ value: 'Tolkien', count: 12 }] }),
        });

        const result = await fetchFacetCounts('language', new URLSearchParams('q=foo'));
        expect(result).toEqual([]);
    });

    test('throws on a non-2xx HTTP response', async() => {
        global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });

        await expect(
            fetchFacetCounts('language', new URLSearchParams('q=foo'))
        ).rejects.toThrow('HTTP 500');
    });

    test('propagates network errors', async() => {
        global.fetch = jest.fn().mockRejectedValue(new TypeError('Failed to fetch'));

        await expect(
            fetchFacetCounts('language', new URLSearchParams('q=foo'))
        ).rejects.toThrow('Failed to fetch');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// mergeFacetCounts
// ─────────────────────────────────────────────────────────────────────────────

describe('mergeFacetCounts', () => {
    // Fixture catalogue (what fetchLanguageOptions() returns)
    const ITEMS = [
        { value: 'English', label: 'English' },
        { value: 'German',  label: 'German'  },
        { value: 'Spanish', label: 'Spanish' },
        { value: 'French',  label: 'French'  },
        { value: 'Dutch',   label: 'Dutch'   },
    ];

    // Fixture counts (what fetchFacetCounts() returns)
    const COUNTS = [
        { value: 'English', label: 'English', count: 665 },
        { value: 'German',  label: 'German',  count: 32  },
        { value: 'Spanish', label: 'Spanish', count: 18  },
    ];

    test('attaches counts to matching items', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const english = result.find(it => it.value === 'English');
        expect(english).toBeDefined();
        expect(english.count).toBe(665);
    });

    test('hides zero-count items when they are not selected', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const values = result.map(it => it.value);
        expect(values).not.toContain('French');
        expect(values).not.toContain('Dutch');
    });

    test('keeps a zero-count item that is currently selected', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, ['French']);
        const french = result.find(it => it.value === 'French');
        expect(french).toBeDefined();
        expect(french.count).toBe(0);
    });

    test('sorts by count descending', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const counts = result.map(it => it.count);
        expect(counts).toEqual([...counts].sort((a, b) => b - a));
    });

    test('zero-count selected item sorts last (count=0)', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, ['French']);
        const last = result[result.length - 1];
        expect(last.value).toBe('French');
        expect(last.count).toBe(0);
    });

    test('preserves original label for each item', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const german = result.find(it => it.value === 'German');
        expect(german.label).toBe('German');
    });

    test('returns empty array when counts is empty', () => {
        // No query → caller passes [] → falls back to uncounted list.
        // This path is never called through merge (caller uses the raw
        // options list directly), but we guard it anyway.
        const result = mergeFacetCounts(ITEMS, [], []);
        expect(result).toHaveLength(0);
    });

    test('returns empty array when items is empty', () => {
        const result = mergeFacetCounts([], COUNTS, []);
        expect(result).toHaveLength(0);
    });

    test('does not mutate the original items array', () => {
        const original = ITEMS.map(it => ({ ...it }));
        mergeFacetCounts(ITEMS, COUNTS, []);
        expect(ITEMS).toEqual(original);
    });

    test('handles multiple selected zero-count items', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, ['French', 'Dutch']);
        const retained = result.filter(it => it.count === 0).map(it => it.value);
        expect(retained).toContain('French');
        expect(retained).toContain('Dutch');
    });
});
