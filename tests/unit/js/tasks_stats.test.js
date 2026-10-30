import { bucketize, pointRadii, splitPeriods } from '../../../openlibrary/plugins/openlibrary/js/tasks_stats.js';

describe('bucketize', () => {
    test('days stay as they are', () => {
        expect(bucketize([1, null, 3], 1).map(b => b.value)).toEqual([1, null, 3]);
    });

    test('periods count back from today, dropping a short one at the start', () => {
        const buckets = bucketize([1, 1, 1, 1, 1, 1, 1, 1, 1], 7);
        expect(buckets.map(b => [b.start, b.end, b.value])).toEqual([[2, 8, 7]]);
    });

    test('a period with no counts is null, not zero', () => {
        expect(bucketize([null, null, 4, null], 2).map(b => b.value)).toEqual([null, 4]);
    });

    test('counts of people sample the rolling window at the period end', () => {
        const rolling = [10, 11, 12, 13];
        expect(bucketize([5, 5, 5, 5], 2, rolling).map(b => b.value)).toEqual([11, 13]);
    });
});

describe('splitPeriods', () => {
    const buckets = [1, 2, 3, 4, 5].map(value => ({ start: 0, end: 0, value }));

    test('the previous period lines up beside the current one', () => {
        const { current, previous } = splitPeriods(buckets, 2);
        expect(current.map(b => b.value)).toEqual([4, 5]);
        expect(previous.map(b => b.value)).toEqual([2, 3]);
    });

    test('pads the previous period where history runs out', () => {
        const { previous } = splitPeriods(buckets, 3);
        expect(previous.map(b => b?.value ?? null)).toEqual([null, 1, 2]);
    });
});

describe('pointRadii', () => {
    test('marks the latest value and any value with no neighbours', () => {
        expect(pointRadii([null, 4, null, 5, 6, null])).toEqual([0, 3, 0, 0, 3, 0]);
    });
});
