import { addEntry, getHistory, clearHistory } from '../../../openlibrary/plugins/openlibrary/js/my-books/store/readingHistory';

const STORAGE_KEY = 'ol_read_history';

/**
 * Returns a fully-populated entry, optionally overriding any fields.
 * @param {Partial<import('../../../openlibrary/plugins/openlibrary/js/my-books/store/readingHistory').ReadHistoryEntry>} overrides
 */
function makeEntry(overrides = {}) {
    return {
        olid: 'OL1W',
        workKey: '/works/OL1W',
        title: 'Test Book',
        coverId: 123,
        coverEditionKey: 'OL1M',
        ocaid: 'testbook00',
        authorNames: ['Author One'],
        timestamp: Date.now(),
        ...overrides,
    };
}

describe('readingHistory store', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    // --- addEntry ---

    it('addEntry stores a single new entry', () => {
        addEntry(makeEntry());

        const history = getHistory();
        expect(history).toHaveLength(1);
        expect(history[0].olid).toBe('OL1W');
        expect(history[0].title).toBe('Test Book');
        expect(history[0].coverId).toBe(123);
        expect(history[0].ocaid).toBe('testbook00');
        expect(history[0].authorNames).toEqual(['Author One']);
    });

    it('addEntry stores all provided metadata fields', () => {
        addEntry(makeEntry({
            olid: 'OL99W',
            workKey: '/works/OL99W',
            title: 'Detailed Book',
            coverId: 456,
            coverEditionKey: 'OL99M',
            ocaid: 'detailedbook00',
            authorNames: ['Alice', 'Bob'],
            timestamp: 1000000,
        }));

        const [entry] = getHistory();
        expect(entry.olid).toBe('OL99W');
        expect(entry.workKey).toBe('/works/OL99W');
        expect(entry.coverId).toBe(456);
        expect(entry.coverEditionKey).toBe('OL99M');
        expect(entry.ocaid).toBe('detailedbook00');
        expect(entry.authorNames).toEqual(['Alice', 'Bob']);
        expect(entry.timestamp).toBe(1000000);
    });

    it('addEntry deduplicates by olid — old record is removed', () => {
        addEntry(makeEntry({ olid: 'OL1W', title: 'First' }));
        addEntry(makeEntry({ olid: 'OL2W', title: 'Second' }));
        addEntry(makeEntry({ olid: 'OL1W', title: 'First (Re-read)', timestamp: Date.now() + 1000 }));

        const history = getHistory();
        expect(history).toHaveLength(2);

        const match = history.find(e => e.olid === 'OL1W');
        expect(match.title).toBe('First (Re-read)');
    });

    it('addEntry promotes re-read entry to front of the list', () => {
        addEntry(makeEntry({ olid: 'OL1W', timestamp: 1000 }));
        addEntry(makeEntry({ olid: 'OL2W', timestamp: 2000 }));
        // Re-read OL1W — it should jump to position 0
        addEntry(makeEntry({ olid: 'OL1W', timestamp: 3000 }));

        const history = getHistory();
        expect(history[0].olid).toBe('OL1W');
        expect(history[1].olid).toBe('OL2W');
    });

    it('addEntry caps the list at 20 entries, dropping the oldest', () => {
        for (let i = 0; i < 25; i++) {
            addEntry(makeEntry({ olid: `OL${i}W`, timestamp: i }));
        }

        const history = getHistory();
        expect(history).toHaveLength(20);
    });

    it('addEntry keeps the most-recently added entries when capping', () => {
        for (let i = 0; i < 25; i++) {
            addEntry(makeEntry({ olid: `OL${i}W`, timestamp: i }));
        }

        // OL24W was added last and should survive the cap
        const history = getHistory();
        const olids = history.map(e => e.olid);
        expect(olids).toContain('OL24W');
        // OL0W was added first (timestamp=0) and must be evicted
        expect(olids).not.toContain('OL0W');
    });

    it('addEntry coerces falsy coverId to null', () => {
        addEntry(makeEntry({ coverId: 0 }));
        expect(getHistory()[0].coverId).toBeNull();
    });

    it('addEntry coerces empty ocaid to null', () => {
        addEntry(makeEntry({ ocaid: '' }));
        expect(getHistory()[0].ocaid).toBeNull();
    });

    it('addEntry coerces empty coverEditionKey to null', () => {
        addEntry(makeEntry({ coverEditionKey: '' }));
        expect(getHistory()[0].coverEditionKey).toBeNull();
    });

    it('addEntry defaults authorNames to an empty array when not provided', () => {
        addEntry(makeEntry({ authorNames: undefined }));
        expect(getHistory()[0].authorNames).toEqual([]);
    });

    it('addEntry uses Date.now() as timestamp when none is provided', () => {
        const before = Date.now();
        addEntry({ olid: 'OL1W', workKey: '/works/OL1W', title: 'T' });
        const after = Date.now();

        const [entry] = getHistory();
        expect(entry.timestamp).toBeGreaterThanOrEqual(before);
        expect(entry.timestamp).toBeLessThanOrEqual(after);
    });

    // --- getHistory ---

    it('getHistory returns an empty array when storage is empty', () => {
        expect(getHistory()).toEqual([]);
    });

    it('getHistory returns entries sorted by timestamp descending', () => {
        const now = Date.now();
        addEntry(makeEntry({ olid: 'OL1W', timestamp: now }));
        addEntry(makeEntry({ olid: 'OL2W', timestamp: now + 2000 }));
        addEntry(makeEntry({ olid: 'OL3W', timestamp: now + 1000 }));

        const history = getHistory();
        expect(history[0].olid).toBe('OL2W');
        expect(history[1].olid).toBe('OL3W');
        expect(history[2].olid).toBe('OL1W');
    });

    it('getHistory does not mutate the stored order', () => {
        // addEntry stores newest-first (unshift), so OL2W is at index 0 in storage
        addEntry(makeEntry({ olid: 'OL1W', timestamp: 1 }));
        addEntry(makeEntry({ olid: 'OL2W', timestamp: 2 }));

        // getHistory sorts a copy; calling it twice must be stable
        const first = getHistory();
        const second = getHistory();
        expect(first.map(e => e.olid)).toEqual(second.map(e => e.olid));
    });

    // --- clearHistory ---

    it('clearHistory empties the list', () => {
        addEntry(makeEntry());
        addEntry(makeEntry({ olid: 'OL2W' }));

        clearHistory();
        expect(getHistory()).toHaveLength(0);
    });

    it('clearHistory removes the localStorage key entirely', () => {
        addEntry(makeEntry());
        clearHistory();
        expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    // --- resilience ---

    it('getHistory returns an empty array on corrupt localStorage data', () => {
        localStorage.setItem(STORAGE_KEY, 'not-valid-json{{{');
        expect(() => getHistory()).not.toThrow();
        expect(getHistory()).toHaveLength(0);
    });

    it('addEntry recovers from corrupt localStorage data and writes a fresh entry', () => {
        localStorage.setItem(STORAGE_KEY, 'not-valid-json{{{');
        expect(() => addEntry(makeEntry())).not.toThrow();
        expect(getHistory()).toHaveLength(1);
    });
});
