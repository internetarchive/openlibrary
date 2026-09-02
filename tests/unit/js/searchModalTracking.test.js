import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';
import { FulltextBand } from '../../../openlibrary/plugins/openlibrary/js/search-modal/fulltextBand.js';

function setup() {
    const modal = new SearchModal();
    modal._track = jest.fn();
    modal._saveCurrentSearch = jest.fn();
    return modal;
}

function clickEvent({ button = 0, modifier = null, defaultPrevented = false } = {}) {
    const event = { button, defaultPrevented, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false };
    if (modifier) event[modifier] = true;
    return event;
}

const WORK = { event: 'ResultClick', label: 'work:3' };

describe('SearchModal result-click tracking', () => {
    test('a plain click tracks, saves the query and flags the row as navigating', () => {
        const modal = setup();

        modal._onResultPress(clickEvent(), '/works/OL1W', WORK);

        expect(modal._track).toHaveBeenCalledWith('ResultClick', 'work:3');
        expect(modal._saveCurrentSearch).toHaveBeenCalled();
        expect(modal._navigatingKey).toBe('/works/OL1W');
    });

    // A new-tab open is still the patron choosing that row, so it counts as a
    // click — it just leaves this page (and so the spinner) alone.
    test.each(['metaKey', 'ctrlKey', 'shiftKey', 'altKey'])(
        '%s-click still tracks and saves, but shows no loading treatment',
        (modifier) => {
            const modal = setup();

            modal._onResultPress(clickEvent({ modifier }), '/works/OL1W', WORK);

            expect(modal._track).toHaveBeenCalledWith('ResultClick', 'work:3');
            expect(modal._saveCurrentSearch).toHaveBeenCalled();
            expect(modal._navigatingKey).toBeNull();
        },
    );

    test('a non-primary button tracks but does not flag the row', () => {
        const modal = setup();

        modal._onResultPress(clickEvent({ button: 1 }), '/works/OL1W', WORK);

        expect(modal._track).toHaveBeenCalledWith('ResultClick', 'work:3');
        expect(modal._navigatingKey).toBeNull();
    });

    test('an already-handled click tracks nothing', () => {
        const modal = setup();

        modal._onResultPress(clickEvent({ defaultPrevented: true }), '/works/OL1W', WORK);

        expect(modal._track).not.toHaveBeenCalled();
        expect(modal._saveCurrentSearch).not.toHaveBeenCalled();
        expect(modal._navigatingKey).toBeNull();
    });

    test('fulltext rows use the same path under their own event name', () => {
        const modal = setup();

        modal._onResultPress(clickEvent({ modifier: 'metaKey' }), 'https://archive.org/details/x', {
            event: 'FulltextClick',
            label: 'rank:2',
        });

        expect(modal._track).toHaveBeenCalledWith('FulltextClick', 'rank:2');
        expect(modal._navigatingKey).toBeNull();
    });

    test('a row pressed without meta saves the query but tracks nothing', () => {
        const modal = setup();

        modal._onResultPress(clickEvent(), '/works/OL1W');

        expect(modal._track).not.toHaveBeenCalled();
        expect(modal._saveCurrentSearch).toHaveBeenCalled();
        expect(modal._navigatingKey).toBe('/works/OL1W');
    });
});

describe('SearchModal fulltext see-all tracking', () => {
    test('a plain click tracks and shows the button spinner', () => {
        const modal = setup();

        modal._onFulltextSeeAll(clickEvent());

        expect(modal._track).toHaveBeenCalledWith('FulltextSeeAll', 'noResults:weakSolr');
        expect(modal._ftSeeAllLoading).toBe(true);
    });

    test('a new-tab click still tracks but leaves the button idle', () => {
        const modal = setup();

        modal._onFulltextSeeAll(clickEvent({ modifier: 'metaKey' }));

        expect(modal._track).toHaveBeenCalledWith('FulltextSeeAll', 'noResults:weakSolr');
        expect(modal._ftSeeAllLoading).toBe(false);
    });

    test('an already-handled click tracks nothing', () => {
        const modal = setup();

        modal._onFulltextSeeAll(clickEvent({ defaultPrevented: true }));

        expect(modal._track).not.toHaveBeenCalled();
        expect(modal._ftSeeAllLoading).toBe(false);
    });
});

describe('SearchModal fulltext see-all label', () => {
    function modalWith({ results = [], query = 'dune', failed = false } = {}) {
        const modal = setup();
        modal._results = results;
        modal._query = query;
        modal._searchFailed = failed;
        return modal;
    }

    const PASSAGE = 'it was the best of times it was';

    test('a weak catalog answer that still returned rows', () => {
        const modal = modalWith({ results: [{}], query: 'hobit' });

        modal._onFulltextSeeAll(clickEvent());

        expect(modal._track).toHaveBeenCalledWith('FulltextSeeAll', 'hasResults:weakSolr');
    });

    test('an empty catalog answer reads as a rescue', () => {
        const modal = modalWith({ results: [] });

        modal._onFulltextSeeAll(clickEvent());

        expect(modal._track).toHaveBeenCalledWith('FulltextSeeAll', 'noResults:weakSolr');
    });

    test('a passage-shaped query is reported as a destination, not a rescue', () => {
        const modal = modalWith({ results: [{}], query: PASSAGE });

        modal._onFulltextSeeAll(clickEvent());

        expect(modal._track).toHaveBeenCalledWith('FulltextSeeAll', 'hasResults:passage');
    });

    // An outage and an honest empty result both leave _results empty; only the
    // flag tells them apart, and the outage is the one worth seeing.
    test('a catalog outage outranks the passage shape', () => {
        const modal = modalWith({ results: [], query: PASSAGE, failed: true });

        modal._onFulltextSeeAll(clickEvent());

        expect(modal._track).toHaveBeenCalledWith('FulltextSeeAll', 'noResults:solrFailed');
    });
});

describe('SearchModal outcome events', () => {
    const KEY = '/search.json?q=dune';

    function settled({ availability = 'all', languages = [] } = {}) {
        const modal = setup();
        modal._activeFetchKey = KEY;
        modal._availability = availability;
        modal._languages = languages;
        return modal;
    }

    beforeEach(() => jest.useFakeTimers());
    afterEach(() => jest.useRealTimers());

    test('an outcome fires only once the query has stood still', () => {
        const modal = settled();

        modal._scheduleOutcomeTrack('NoResults', KEY);
        expect(modal._track).not.toHaveBeenCalled();

        jest.runAllTimers();
        expect(modal._track).toHaveBeenCalledWith('NoResults', 'unfiltered');
    });

    test('a query that moved on before the window elapsed is not counted', () => {
        const modal = settled();

        modal._scheduleOutcomeTrack('NoResults', KEY);
        modal._activeFetchKey = '/search.json?q=dune+messiah';
        jest.runAllTimers();

        expect(modal._track).not.toHaveBeenCalled();
    });

    test('re-settling the same key in one modal session fires once', () => {
        const modal = settled();

        modal._scheduleOutcomeTrack('ResultsShown', KEY);
        jest.runAllTimers();
        modal._scheduleOutcomeTrack('ResultsShown', KEY);
        jest.runAllTimers();

        expect(modal._track).toHaveBeenCalledTimes(1);
    });

    test('the label names the active filter categories', () => {
        const modal = settled({ availability: 'readable', languages: ['ger'] });

        modal._scheduleOutcomeTrack('ResultsShown', KEY);
        jest.runAllTimers();

        expect(modal._track).toHaveBeenCalledWith('ResultsShown', 'availability+language');
    });

    // The regression that forced per-action timers: a band outcome landing
    // inside the catalog outcome's window used to cancel it, deleting the
    // denominator of the very ratio these events exist to compute.
    test('a band outcome does not cancel the catalog outcome beside it', () => {
        const modal = settled();
        modal._visibleFtHits = () => [{}, {}];

        modal._scheduleOutcomeTrack('NoResults', KEY);
        modal._scheduleBandOutcome('resolved');
        jest.runAllTimers();

        expect(modal._track).toHaveBeenCalledWith('NoResults', 'unfiltered');
        expect(modal._track).toHaveBeenCalledWith('FulltextBand', 'shown:2');
        expect(modal._track).toHaveBeenCalledTimes(2);
    });

    test('a band outcome counts rows that survived the dedupe, not the fetched pool', () => {
        const modal = settled();
        modal._ftHits = [{}, {}, {}, {}, {}];
        modal._visibleFtHits = () => [];

        modal._scheduleBandOutcome('resolved');
        jest.runAllTimers();

        expect(modal._track).toHaveBeenCalledWith('FulltextBand', 'empty');
    });

    test('a failed band attempt is counted apart from an empty one', () => {
        const modal = settled();

        modal._scheduleBandOutcome('failed');
        jest.runAllTimers();

        expect(modal._track).toHaveBeenCalledWith('FulltextBand', 'failed');
    });

    test('a band attempt with no catalog search behind it is dropped', () => {
        const modal = settled();
        modal._activeFetchKey = null;

        modal._scheduleBandOutcome('resolved');
        jest.runAllTimers();

        expect(modal._track).not.toHaveBeenCalled();
    });

    test('closing the modal drops every pending outcome', () => {
        const modal = settled();

        modal._scheduleOutcomeTrack('NoResults', KEY);
        modal._scheduleBandOutcome('resolved');
        modal._clearOutcomeTimers();
        jest.runAllTimers();

        expect(modal._track).not.toHaveBeenCalled();
    });
});

describe('FulltextBand attempt reporting', () => {
    const FILTERS = { readable: false, languages: [] };

    const flush = () => new Promise(resolve => setTimeout(resolve, 0));

    function band(onAttempt) {
        return new FulltextBand({
            getFilters: () => FILTERS,
            onChange: () => {},
            onAttempt,
        });
    }

    test('a resolved fetch reports the attempt', async() => {
        global.fetch = jest.fn().mockResolvedValue({
            ok: true,
            json: async() => ({ hits: { hits: [], total: 0 } }),
        });
        const onAttempt = jest.fn();

        band(onAttempt).solrFailed('dune');
        await flush();

        expect(onAttempt).toHaveBeenCalledWith('resolved');
    });

    test('a failed fetch reports the attempt too, so it is not lost', async() => {
        global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 502 });
        const onAttempt = jest.fn();

        band(onAttempt).solrFailed('dune');
        await flush();

        expect(onAttempt).toHaveBeenCalledWith('failed');
    });

    test('a band that never fetches reports nothing', () => {
        global.fetch = jest.fn();
        const onAttempt = jest.fn();

        // A strong catalog answer clears the band instead of calling out.
        band(onAttempt).solrSettled('dune', [{ title: 'Dune' }]);

        expect(global.fetch).not.toHaveBeenCalled();
        expect(onAttempt).not.toHaveBeenCalled();
    });
});

// The bias these exist to remove: an outcome scheduled on the idle window used
// to die with the page when the patron acted before the window elapsed, so the
// fastest searches — which skew toward good catalog answers — never reached the
// denominator that every rate is computed against.
describe('SearchModal outcome flushing', () => {
    const KEY = '/search.json?q=dune';

    function pending({ results = [{}] } = {}) {
        const modal = setup();
        modal._activeFetchKey = KEY;
        modal._results = results;
        modal._query = 'dune';
        modal._visibleFtHits = () => [];
        modal._scheduleOutcomeTrack('ResultsShown', KEY);
        return modal;
    }

    beforeEach(() => jest.useFakeTimers());
    afterEach(() => jest.useRealTimers());

    test('pressing a result settles the search before the click is counted', () => {
        const modal = pending();

        modal._onResultPress(clickEvent(), '/works/OL1W', { event: 'ResultClick', label: 'work:1' });

        expect(modal._track).toHaveBeenNthCalledWith(1, 'ResultsShown', 'unfiltered');
        expect(modal._track).toHaveBeenNthCalledWith(2, 'ResultClick', 'work:1');
    });

    test('the catalog see-all settles the search it is leaving', () => {
        const modal = pending();
        modal._buildSearchUrl = () => '/search?q=dune';
        modal._saveCurrentSearch = jest.fn();
        modal._navigate = jest.fn();

        modal._onSeeAllResults();

        expect(modal._track).toHaveBeenNthCalledWith(1, 'ResultsShown', 'unfiltered');
        expect(modal._track).toHaveBeenNthCalledWith(2, 'SeeAllResults', 'hasResults');
    });

    test('the fulltext see-all settles the search it is leaving', () => {
        const modal = pending();

        modal._onFulltextSeeAll(clickEvent());

        expect(modal._track).toHaveBeenNthCalledWith(1, 'ResultsShown', 'unfiltered');
        expect(modal._track).toHaveBeenNthCalledWith(2, 'FulltextSeeAll', 'hasResults:weakSolr');
    });

    // Abandonment is an outcome, not an absence of one.
    test('closing the modal settles a pending outcome instead of dropping it', () => {
        const modal = pending({ results: [] });

        modal._onDialogClosed();

        expect(modal._track).toHaveBeenCalledWith('ResultsShown', 'unfiltered');
    });

    test('a flushed outcome is not counted again when its timer would have fired', () => {
        const modal = pending();

        modal._flushOutcomes();
        jest.runAllTimers();

        expect(modal._track).toHaveBeenCalledTimes(1);
    });

    test('flushing settles the catalog and band outcomes together', () => {
        const modal = pending({ results: [] });
        modal._visibleFtHits = () => [{}, {}, {}];
        modal._scheduleBandOutcome('resolved');

        modal._flushOutcomes();

        expect(modal._track).toHaveBeenCalledWith('ResultsShown', 'unfiltered');
        expect(modal._track).toHaveBeenCalledWith('FulltextBand', 'shown:3');
        expect(modal._track).toHaveBeenCalledTimes(2);
    });

    // A flush still only reports the query that is actually current — an exit
    // taken while a superseded search was pending must not resurrect it.
    test('flushing does not settle an outcome whose query moved on', () => {
        const modal = pending();
        modal._activeFetchKey = '/search.json?q=dune+messiah';

        modal._flushOutcomes();

        expect(modal._track).not.toHaveBeenCalled();
    });

    test('a reset still drops pending outcomes rather than settling them', () => {
        const modal = pending();

        modal._resetResults({ hasSearched: false });
        jest.runAllTimers();

        expect(modal._track).not.toHaveBeenCalled();
    });
});
