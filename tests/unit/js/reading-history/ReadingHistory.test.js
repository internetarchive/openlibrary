import { ReadingHistory } from '../../../../openlibrary/plugins/openlibrary/js/reading-history/ReadingHistory';

describe('ReadingHistory', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    afterEach(() => {
        localStorage.clear();
    });

    test('adds entry to reading history', () => {
        ReadingHistory.add('OL123456M');
        const entries = ReadingHistory.getAll();
        expect(entries.length).toBe(1);
        expect(entries[0].editionId).toBe('OL123456M');
        expect(entries[0].timestamp).toBeGreaterThan(0);
    });

    test('deduplicates entries keeping most recent', () => {
        ReadingHistory.add('OL123456M');
        const firstTimestamp = ReadingHistory.getAll()[0].timestamp;

        // Wait a bit and add again
        setTimeout(() => {
            ReadingHistory.add('OL123456M');
            const entries = ReadingHistory.getAll();
            expect(entries.length).toBe(1);
            expect(entries[0].editionId).toBe('OL123456M');
            expect(entries[0].timestamp).toBeGreaterThan(firstTimestamp);
        }, 10);
    });

    test('limits to MAX_ITEMS', () => {
        // Add more than MAX_ITEMS
        for (let i = 0; i < 150; i++) {
            ReadingHistory.add(`OL${i}M`);
        }
        const entries = ReadingHistory.getAll();
        expect(entries.length).toBe(100); // MAX_ITEMS
    });

    test('getEditionIds returns most recent first', () => {
        ReadingHistory.add('OL1M');
        ReadingHistory.add('OL2M');
        ReadingHistory.add('OL3M');

        const ids = ReadingHistory.getEditionIds();
        expect(ids[0]).toBe('OL3M');
        expect(ids[1]).toBe('OL2M');
        expect(ids[2]).toBe('OL1M');
    });

    test('getEditionIds respects limit', () => {
        ReadingHistory.add('OL1M');
        ReadingHistory.add('OL2M');
        ReadingHistory.add('OL3M');

        const ids = ReadingHistory.getEditionIds(2);
        expect(ids.length).toBe(2);
        expect(ids[0]).toBe('OL3M');
        expect(ids[1]).toBe('OL2M');
    });

    test('clear removes all entries', () => {
        ReadingHistory.add('OL123456M');
        ReadingHistory.clear();
        expect(ReadingHistory.getAll().length).toBe(0);
    });

    test('getCount returns correct number', () => {
        ReadingHistory.add('OL1M');
        ReadingHistory.add('OL2M');
        expect(ReadingHistory.getCount()).toBe(2);
    });

    test('handles empty editionId gracefully', () => {
        ReadingHistory.add('');
        ReadingHistory.add(null);
        ReadingHistory.add(undefined);
        expect(ReadingHistory.getAll().length).toBe(0);
    });

    test('handles corrupted localStorage data', () => {
        localStorage.setItem('ol_reading_history', 'not valid json');
        const entries = ReadingHistory.getAll();
        expect(Array.isArray(entries)).toBe(true);
        expect(entries.length).toBe(0);
    });

    test('isAvailable returns true when localStorage works', () => {
        expect(ReadingHistory.isAvailable()).toBe(true);
    });
});

