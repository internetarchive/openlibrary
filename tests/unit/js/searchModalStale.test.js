/**
 * The search modal's stale treatment: results linger through an edit so the
 * list doesn't flicker, and once they've lingered past STALE_DELAY_MS they're
 * dimmed rather than left passing for the answer to what's now in the input.
 * Exercised on a bare SearchModal instance, as the other search-modal suites do.
 */
import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';

const STALE_DELAY_MS = 300;

function modalSetup({ query = 'white whale' } = {}) {
    const modal = new SearchModal();
    modal._query = query;
    modal._languages = [];
    return modal;
}

/** A modal whose rows answer `answered` while `query` is what's typed. */
function withCatalog({ query, answered }) {
    const modal = modalSetup({ query: answered });
    modal._results = [{ key: '/works/OL1W' }];
    modal._resultsKey = modal._buildSearchJsonUrl(answered);
    modal._query = query;
    return modal;
}

/** A modal whose band hits answer `answered` while `query` is what's typed. */
function withBand({ query, answered }) {
    const modal = modalSetup({ query: answered });
    modal._ftHits = [{ ia: 'mobydick00melv' }];
    modal._ftSearchKey = `q=${encodeURIComponent(answered).replace(/%20/g, '+')}`;
    modal._query = query;
    return modal;
}

describe('what counts as superseded', () => {
    test('rows fetched for the query on screen are current', () => {
        expect(withCatalog({ query: 'white whale', answered: 'white whale' })._catalogSuperseded()).toBe(false);
    });

    test('an edit supersedes them', () => {
        expect(withCatalog({ query: 'white whales', answered: 'white whale' })._catalogSuperseded()).toBe(true);
    });

    // Same query, different search — the rows answer the unfiltered one.
    test('so does a filter toggle', () => {
        const modal = withCatalog({ query: 'white whale', answered: 'white whale' });
        modal._availability = 'readable';
        expect(modal._catalogSuperseded()).toBe(true);
    });

    test('an empty list has nothing to supersede', () => {
        const modal = withCatalog({ query: 'white whales', answered: 'white whale' });
        modal._results = [];
        expect(modal._catalogSuperseded()).toBe(false);
    });

    test('the band is superseded on the same terms', () => {
        expect(withBand({ query: 'white whale', answered: 'white whale' })._bandSuperseded()).toBe(false);
        expect(withBand({ query: 'white whales', answered: 'white whale' })._bandSuperseded()).toBe(true);
    });
});

describe('the stale delay', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    test('superseded rows hold at full strength inside the delay', () => {
        const modal = withCatalog({ query: 'white whales', answered: 'white whale' });

        modal.updated();
        vi.advanceTimersByTime(STALE_DELAY_MS - 1);

        expect(modal._markStale).toBe(false);
        expect(modal._catalogIsStale()).toBe(false);
    });

    test('and are marked once it passes', () => {
        const modal = withCatalog({ query: 'white whales', answered: 'white whale' });

        modal.updated();
        vi.advanceTimersByTime(STALE_DELAY_MS);

        expect(modal._markStale).toBe(true);
        expect(modal._catalogIsStale()).toBe(true);
    });

    // The point of the delay: a local Solr answer lands well inside it, so the
    // list never strobes on a keystroke the patron barely finished typing.
    test('an answer that lands first is never marked', () => {
        const modal = withCatalog({ query: 'white whales', answered: 'white whale' });

        modal.updated();
        vi.advanceTimersByTime(150);
        // The new answer arrives.
        modal._resultsKey = modal._buildSearchJsonUrl('white whales');
        modal.updated();
        vi.advanceTimersByTime(STALE_DELAY_MS);

        expect(modal._markStale).toBe(false);
    });

    test('a fresh answer clears a mark already showing', () => {
        const modal = withCatalog({ query: 'white whales', answered: 'white whale' });
        modal.updated();
        vi.advanceTimersByTime(STALE_DELAY_MS);

        modal._resultsKey = modal._buildSearchJsonUrl('white whales');
        modal.updated();

        expect(modal._markStale).toBe(false);
        expect(modal._catalogIsStale()).toBe(false);
    });

    // One clock for the modal, so the band keeps its dim through the moment the
    // catalog catches up — which on the Books tab is the common case, the
    // fulltext backend being much the slower of the two.
    test('the clock keeps running while only the band is behind', () => {
        const modal = withCatalog({ query: 'white whales', answered: 'white whale' });
        modal._ftHits = [{ ia: 'mobydick00melv' }];
        modal._ftSearchKey = 'q=white+whale';
        modal.updated();
        vi.advanceTimersByTime(STALE_DELAY_MS);

        modal._resultsKey = modal._buildSearchJsonUrl('white whales');
        modal.updated();

        expect(modal._catalogIsStale()).toBe(false);
        expect(modal._bandIsStale()).toBe(true);
    });

    test('a repeat reconcile does not restart the clock', () => {
        const modal = withCatalog({ query: 'white whales', answered: 'white whale' });

        modal.updated();
        vi.advanceTimersByTime(200);
        modal.updated();
        vi.advanceTimersByTime(100);

        expect(modal._markStale).toBe(true);
    });

    test('a query dropped below the autocomplete threshold leaves no dim behind', () => {
        const modal = withCatalog({ query: 'wh', answered: 'white whale' });
        modal.updated();
        vi.advanceTimersByTime(STALE_DELAY_MS);
        expect(modal._markStale).toBe(true);

        // What _onQueryInput does on the way down.
        modal._resetResults({ hasSearched: false });
        modal._ftHits = [];
        modal.updated();

        expect(modal._markStale).toBe(false);
    });
});

describe('the results container class', () => {
    test('marks a stale list', () => {
        expect(modalSetup()._resultsClass(true)).toBe('results is-stale');
        expect(modalSetup()._resultsClass(false)).toBe('results');
    });

    // Both dims are an opacity on the same element, so they'd compound. A press
    // is the stronger signal, and it's the one the patron just made.
    test('a press supersedes the stale dim rather than compounding with it', () => {
        const modal = modalSetup();
        modal._navigatingKey = '/works/OL1W';
        expect(modal._resultsClass(true)).toBe('results is-navigating');
    });
});
