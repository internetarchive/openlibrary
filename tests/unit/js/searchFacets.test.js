/**
 * Unit tests for fetchFacetCounts() and mergeFacetCounts() (searchFacets.js),
 * shared by the /search filter bar and the header search modal.
 *
 * Run with: jest (or vitest — both work without config changes)
 *
 * Issue: #13060  —  feat(search): Wire facet droppers to context-aware counts
 */

import {
    FACET_OPEN_BUDGET_MS,
    fetchFacetCounts,
    mergeFacetCounts,
    openWhenCountsReady,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/searchFacets.js';

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

    test('strips an existing filter on the field being counted', async() => {
        // Solr ANDs an fq on the faceted field, so forwarding language=eng would
        // zero out every other language and strand the patron on one choice.
        global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async() => MOCK_FLAT });

        await fetchFacetCounts('language', new URLSearchParams('q=tolkien&language=eng&public_scan=true'));

        const url = new URL(global.fetch.mock.calls[0][0], 'https://openlibrary.org');
        expect(url.searchParams.getAll('language')).toEqual([]);
        expect(url.searchParams.get('field')).toBe('language');
        // Filters on *other* fields still narrow the counts and must survive.
        expect(url.searchParams.get('public_scan')).toBe('true');
        expect(url.searchParams.get('q')).toBe('tolkien');
    });

    test('strips both spellings of the author filter when counting author_facet', async() => {
        global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async() => MOCK_FLAT });

        await fetchFacetCounts('author_facet', new URLSearchParams('q=rings&author_facet=OL9A&author_key=OL9A'));

        const url = new URL(global.fetch.mock.calls[0][0], 'https://openlibrary.org');
        expect(url.searchParams.getAll('author_key')).toEqual([]);
        expect(url.searchParams.getAll('author_facet')).toEqual([]);
    });

    test('does not mutate the caller\'s params', async() => {
        global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async() => MOCK_FLAT });

        const params = new URLSearchParams('q=tolkien&language=eng');
        await fetchFacetCounts('language', params);
        expect(params.getAll('language')).toEqual(['eng']);
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
    // Fixture catalogue (what fetchLanguageOptions() returns): the value is the
    // MARC code, the label is the patron-facing name.
    const ITEMS = [
        { value: 'eng', label: 'English' },
        { value: 'ger', label: 'German'  },
        { value: 'spa', label: 'Spanish' },
        { value: 'fre', label: 'French'  },
        { value: 'dut', label: 'Dutch'   },
    ];

    // Fixture counts (what fetchFacetCounts() returns)
    const COUNTS = [
        { value: 'eng', label: 'English', count: 665 },
        { value: 'ger', label: 'German',  count: 32  },
        { value: 'spa', label: 'Spanish', count: 18  },
    ];

    test('attaches counts to matching items', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const english = result.find(it => it.value === 'eng');
        expect(english).toBeDefined();
        expect(english.count).toBe(665);
    });

    test('joins on value, not label', () => {
        // Both sides localize their labels independently, so a label join would
        // silently drop every row under some UI languages.
        const frenchLabels = COUNTS.map(c => ({ ...c, label: `${c.label} (fr)` }));
        const result = mergeFacetCounts(ITEMS, frenchLabels, []);
        expect(result.map(it => it.value)).toEqual(['eng', 'ger', 'spa']);
        expect(result.find(it => it.value === 'eng').count).toBe(665);
    });

    test('hides zero-count items when they are not selected', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const values = result.map(it => it.value);
        expect(values).not.toContain('fre');
        expect(values).not.toContain('dut');
    });

    test('keeps a zero-count item that is currently selected', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, ['fre']);
        const french = result.find(it => it.value === 'fre');
        expect(french).toBeDefined();
        expect(french.count).toBe(0);
    });

    test('sorts by count descending', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const counts = result.map(it => it.count);
        expect(counts).toEqual([...counts].sort((a, b) => b - a));
    });

    test('zero-count selected item sorts last (count=0)', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, ['fre']);
        const last = result[result.length - 1];
        expect(last.value).toBe('fre');
        expect(last.count).toBe(0);
    });

    test('preserves original label for each item', () => {
        const result = mergeFacetCounts(ITEMS, COUNTS, []);
        const german = result.find(it => it.value === 'ger');
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
        const result = mergeFacetCounts(ITEMS, COUNTS, ['fre', 'dut']);
        const retained = result.filter(it => it.count === 0).map(it => it.value);
        expect(retained).toContain('fre');
        expect(retained).toContain('dut');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// openWhenCountsReady
// ─────────────────────────────────────────────────────────────────────────────

describe('openWhenCountsReady', () => {
    /** Stands in for the ol-select-popover and its request-open event. */
    function requestOpenEvent({ focusFirst = false } = {}) {
        const popover = { show: jest.fn() };
        return {
            currentTarget: popover,
            detail: { focusFirst },
            preventDefault: jest.fn(),
            popover,
        };
    }

    beforeEach(() => {
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    test('holds the panel shut until the load resolves', async() => {
        const e = requestOpenEvent();
        let release;
        const load = () => new Promise(resolve => { release = resolve; });

        const done = openWhenCountsReady(e, load);
        await Promise.resolve();

        expect(e.preventDefault).toHaveBeenCalled();
        expect(e.popover.show).not.toHaveBeenCalled();

        release();
        await done;
        expect(e.popover.show).toHaveBeenCalledWith({ focusFirst: false });
    });

    test('forwards the keyboard focus-first intent to show()', async() => {
        const e = requestOpenEvent({ focusFirst: true });
        await openWhenCountsReady(e, () => Promise.resolve());
        expect(e.popover.show).toHaveBeenCalledWith({ focusFirst: true });
    });

    test('opens anyway once the budget expires', async() => {
        const e = requestOpenEvent();
        const done = openWhenCountsReady(e, () => new Promise(() => {}));  // never settles
        await Promise.resolve();
        expect(e.popover.show).not.toHaveBeenCalled();

        jest.advanceTimersByTime(FACET_OPEN_BUDGET_MS);
        await done;
        expect(e.popover.show).toHaveBeenCalledTimes(1);
    });

    test('opens when the load rejects', async() => {
        const e = requestOpenEvent();
        await expect(openWhenCountsReady(e, () => Promise.reject(new Error('boom'))))
            .rejects.toThrow('boom');
        expect(e.popover.show).toHaveBeenCalledTimes(1);
    });

    test('clears the budget timer once the load wins the race', async() => {
        const e = requestOpenEvent();
        await openWhenCountsReady(e, () => Promise.resolve());

        jest.advanceTimersByTime(FACET_OPEN_BUDGET_MS * 2);
        expect(e.popover.show).toHaveBeenCalledTimes(1);
    });
});
