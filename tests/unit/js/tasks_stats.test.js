import { bucketize, cardChange, pointRadii, ratio, shiftPeriods, subtract } from '../../../openlibrary/plugins/openlibrary/js/tasks_stats.js';

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

describe('subtract', () => {
    test('takes the others away day by day, never below zero', () => {
        expect(subtract([10, 5, null, 3], [4, 1, 1, 2], [1, 0, 0, 5])).toEqual([5, 4, null, 0]);
    });

    test('is null where any part is missing', () => {
        expect(subtract([10], [null])).toEqual([null]);
    });
});

describe('ratio', () => {
    const buckets = (/** @type {(number | null)[]} */ values) => values.map((value, i) => ({ start: i, end: i, value }));

    test('scales each period and skips ones without a denominator', () => {
        expect(ratio(buckets([5, 3, null]), buckets([1000, 0, 10]), 1000).map(b => b.value)).toEqual([5, null, null]);
    });
});

describe('shiftPeriods', () => {
    const buckets = [1, 2, 3, 4, 5, 6].map(value => ({ start: 0, end: 0, value }));

    test('each bucket sits beside the one `shift` before it', () => {
        const { current, previous } = shiftPeriods(buckets, 3, 2);
        expect(current.map(b => b.value)).toEqual([4, 5, 6]);
        expect(previous.map(b => b?.value ?? null)).toEqual([2, 3, 4]);
    });

    test('pads where history runs out', () => {
        const { previous } = shiftPeriods(buckets, 4, 3);
        expect(previous.map(b => b?.value ?? null)).toEqual([null, 1, 2, 3]);
    });
});

describe('cardChange', () => {
    test('reads like the server: a direction and one decimal', () => {
        expect(cardChange(120, 100)).toEqual({ direction: 'up', text: '20.0%' });
        expect(cardChange(90, 100)).toEqual({ direction: 'down', text: '10.0%' });
        expect(cardChange(100, 100)?.direction).toBe('flat');
    });

    test('needs both values', () => {
        expect(cardChange(null, 5)).toBeNull();
        expect(cardChange(5, 0)).toBeNull();
        expect(cardChange(5, null)).toBeNull();
    });
});

describe('pointRadii', () => {
    test('marks the latest value and any value with no neighbours', () => {
        expect(pointRadii([null, 4, null, 5, 6, null])).toEqual([0, 3, 0, 0, 3, 0]);
    });
});
