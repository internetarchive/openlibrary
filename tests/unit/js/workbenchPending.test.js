/**
 * The workbench's staged field edits: grouped one (field, value) per batch, and
 * only the field a batch actually wrote is cleared afterwards, so a second
 * staged field on the same record is not lost when the first is applied.
 */
import { groupPending, countPending, withoutApplied } from '../../../openlibrary/components/lit/utils/workbench-pending.js';

const pending = {
    '/books/OL1M': { publishers: ['Penguin'], publish_date: '1999' },
    '/books/OL2M': { publishers: ['Penguin'] },
    '/books/OL3M': { publishers: ['Vintage'] },
};

describe('groupPending', () => {
    test('groups by field and value, keeping the records of each', () => {
        const groups = groupPending(pending);
        expect(groups).toEqual([
            { field: 'publishers', value: ['Penguin'], keys: ['/books/OL1M', '/books/OL2M'] },
            { field: 'publish_date', value: '1999', keys: ['/books/OL1M'] },
            { field: 'publishers', value: ['Vintage'], keys: ['/books/OL3M'] },
        ]);
    });

    test('is empty for nothing staged', () => {
        expect(groupPending({})).toEqual([]);
        expect(groupPending(undefined)).toEqual([]);
        expect(countPending({})).toBe(0);
    });
});

describe('countPending', () => {
    test('counts (record, field) pairs', () => {
        expect(countPending(pending)).toBe(4);
    });
});

describe('withoutApplied', () => {
    test('clears only the applied field on the touched records', () => {
        const next = withoutApplied(pending, ['/books/OL1M', '/books/OL2M'], 'set_field', { field: 'publishers', value: ['Penguin'] });
        expect(next).toEqual({
            '/books/OL1M': { publish_date: '1999' },
            '/books/OL3M': { publishers: ['Vintage'] },
        });
        expect(groupPending(next)).toHaveLength(2);
    });

    test('leaves everything staged after any other action', () => {
        expect(withoutApplied(pending, ['/books/OL1M'], 'set_author', { author: '/authors/OL1A' })).toBe(pending);
        expect(withoutApplied(pending, ['/books/OL1M'], 'set_field', null)).toBe(pending);
    });

    test('drops a record once nothing is staged on it', () => {
        const next = withoutApplied({ '/books/OL9M': { series: ['x'] } }, ['/books/OL9M'], 'set_field', { field: 'series' });
        expect(next).toEqual({});
    });
});
