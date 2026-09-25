/**
 * The search modal's Books / Inside books tabs and the fulltext explicit mode.
 */
import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';
import { FulltextBand, INSIDE_LIMIT } from '../../../openlibrary/plugins/openlibrary/js/search-modal/fulltextBand.js';

/** A band whose fetches are recorded rather than performed. */
function bandSetup() {
    const band = new FulltextBand({
        getFilters: () => ({ readable: false, languages: [] }),
        onChange: vi.fn(),
    });
    band._fetch = vi.fn();
    return band;
}

function modalSetup({ query = 'white whale' } = {}) {
    const modal = new SearchModal();
    modal._track = vi.fn();
    modal._navigate = vi.fn();
    modal._saveCurrentSearch = vi.fn();
    modal._debouncedFetch = vi.fn();
    modal._query = query;
    // No render root on a bare instance for _selectMode to focus.
    Object.defineProperty(modal, 'updateComplete', { value: { then: () => {} } });
    return modal;
}

describe('FulltextBand explicit mode', () => {
    test('entering the tab fetches at once, at the tab\'s deeper limit', () => {
        const band = bandSetup();

        band.setExplicit(true, 'white whale');

        expect(band.explicit).toBe(true);
        expect(band._fetch).toHaveBeenCalledWith('white whale', INSIDE_LIMIT);
    });

    // Entering with no query still calls through, so the real _fetch's
    // short-circuit is what has to keep the tab out of a spinner.
    test('entering with nothing to search leaves the tab idle, not loading', () => {
        const band = new FulltextBand({
            getFilters: () => ({ readable: false, languages: [] }),
            onChange: vi.fn(),
        });

        band.setExplicit(true, '   ');

        expect(band.explicit).toBe(true);
        expect(band.loading).toBe(false);
    });

    test('re-entering the same mode is a no-op', () => {
        const band = bandSetup();

        band.setExplicit(false, 'white whale');

        expect(band._fetch).not.toHaveBeenCalled();
    });

    test('leaving the tab drops the hits it fetched', () => {
        const band = bandSetup();
        band.explicit = true;
        band.hits = [{ ia: 'scanA' }];
        band.total = 42;

        band.setExplicit(false);

        expect(band.explicit).toBe(false);
        expect(band.hits).toEqual([]);
        expect(band.total).toBeNull();
    });

    // The band's gates exist to spare the FTS backend; the tab is a request.
    test('a strong catalog answer no longer clears the tab\'s hits', () => {
        const band = bandSetup();
        band.explicit = true;
        band.hits = [{ ia: 'scanA' }];

        band.solrSettled('white whale', [{ title: 'White whale' }]);

        expect(band.hits).toEqual([{ ia: 'scanA' }]);
        expect(band._fetch).not.toHaveBeenCalled();
    });

    test('a failed catalog search does not rescue-fetch for the tab', () => {
        const band = bandSetup();
        band.explicit = true;

        band.solrFailed('white whale');

        expect(band._fetch).not.toHaveBeenCalled();
    });

    describe('with fake timers', () => {
        beforeEach(() => vi.useFakeTimers());
        afterEach(() => vi.useRealTimers());

        test('every query fetches on the tab, passage or not', () => {
            const band = bandSetup();
            band.explicit = true;

            band.queryChanged('dune');
            vi.runAllTimers();

            expect(band._fetch).toHaveBeenCalledWith('dune', INSIDE_LIMIT);
        });

        test('off the tab, a short query still waits for the catalog\'s answer', () => {
            const band = bandSetup();

            band.queryChanged('dune');
            vi.runAllTimers();

            expect(band._fetch).not.toHaveBeenCalled();
        });

        // The timers test the mode at fire time, so a switch cancels the other's.
        test('leaving the tab cancels a fetch it had queued', () => {
            const band = bandSetup();
            band.explicit = true;
            band.queryChanged('dune');

            band.explicit = false;
            vi.runAllTimers();

            expect(band._fetch).not.toHaveBeenCalled();
        });

        test('the tab shows a spinner before its debounce fires', () => {
            const band = bandSetup();
            band.explicit = true;

            band.queryChanged('dune');

            expect(band.loading).toBe(true);
        });

        test('an emptied query on the tab stops loading', () => {
            const band = bandSetup();
            band.explicit = true;
            band.loading = true;

            band.queryChanged('   ');

            expect(band.loading).toBe(false);
        });
    });
});

describe('SearchModal scope tabs', () => {
    test('picking the Inside tab puts the band in explicit mode and tracks it', () => {
        const modal = modalSetup();

        modal._selectMode('inside');

        expect(modal._inside).toBe(true);
        expect(modal._ftBand.explicit).toBe(true);
        expect(modal._track).toHaveBeenCalledWith('Tab', 'inside');
    });

    test('the Inside tab does not fetch the catalog', () => {
        const modal = modalSetup();
        modal._selectMode('inside');
        modal._debouncedFetch.mockClear();

        modal._scheduleSearch();

        expect(modal._debouncedFetch).not.toHaveBeenCalled();
    });

    test('the Books tab does', () => {
        const modal = modalSetup();

        modal._scheduleSearch();

        expect(modal._debouncedFetch).toHaveBeenCalled();
    });

    // The catalog paused while Inside was showing, so Books must catch up.
    test('coming back to Books refetches a catalog that fell behind', () => {
        const modal = modalSetup();
        modal._selectMode('inside');
        modal._query = 'it was the best of times';
        modal._debouncedFetch.mockClear();

        modal._selectMode('books');

        expect(modal._debouncedFetch).toHaveBeenCalled();
    });

    test('a catalog still current for the query is left alone, and the band re-armed', () => {
        const modal = modalSetup();
        modal._activeFetchKey = modal._buildSearchJsonUrl('white whale');
        modal._hasSearched = true;
        modal._results = [{ title: 'Moby Dick' }];
        modal._selectMode('inside');
        modal._debouncedFetch.mockClear();
        const solrSettled = vi.spyOn(modal._ftBand, 'solrSettled');

        modal._selectMode('books');

        expect(modal._debouncedFetch).not.toHaveBeenCalled();
        expect(solrSettled).toHaveBeenCalledWith('white whale', modal._results);
    });

    test('closing the modal returns the next visit to Books', () => {
        const modal = modalSetup();
        modal._selectMode('inside');

        modal._onDialogClosed();

        expect(modal._inside).toBe(false);
        expect(modal._ftBand.explicit).toBe(false);
    });

    test('Enter on the Inside tab commits to the full-page fulltext search', () => {
        const modal = modalSetup();
        modal._selectMode('inside');

        modal._onInputKeydown({ key: 'Enter', preventDefault: () => {} });

        expect(modal._navigate).toHaveBeenCalledWith('/search/inside?q=white+whale');
        expect(modal._track).toHaveBeenCalledWith('FulltextSeeAll', 'noResults:tab');
        expect(modal._ftSeeAllLoading).toBe(true);
    });

    test('the tab names itself as the reason the fulltext rows showed', () => {
        const modal = modalSetup();
        modal._searchFailed = true;
        modal._selectMode('inside');

        expect(modal._fulltextSeeAllLabel()).toBe('noResults:tab');
    });

    // The bug this guards: the callers raised the catalog spinner, but the
    // Inside tab skips the fetch that lowers it, so it never came down — the
    // Books tab then showed "Searching…" forever with nothing in flight.
    test('typing on the Inside tab never raises the catalog spinner', () => {
        const modal = modalSetup();
        modal._selectMode('inside');

        modal._onQueryInput({ target: { value: 'white whales' } });

        expect(modal._loading).toBe(false);
    });

    test('a filter toggle on the Inside tab does not either', () => {
        const modal = modalSetup();
        modal._selectMode('inside');

        modal._setAvailability('readable');

        expect(modal._loading).toBe(false);
    });

    test('an edit made on the Inside tab is searched on return to Books', () => {
        const modal = modalSetup();
        modal._selectMode('inside');
        modal._onQueryInput({ target: { value: 'white whales' } });
        modal._debouncedFetch.mockClear();

        modal._selectMode('books');

        expect(modal._loading).toBe(true);
        expect(modal._debouncedFetch).toHaveBeenCalled();
    });

    // Focus follows selection, so a held arrow key would flip tabs at the
    // key-repeat rate, fetching fulltext on every flip.
    test('a held arrow key flips the tab once, not once per repeat', () => {
        const modal = modalSetup();
        const press = (repeat) => modal._onTabKeydown({ key: 'ArrowRight', repeat, preventDefault: () => {} });

        press(false);
        expect(modal._inside).toBe(true);

        press(true);
        press(true);
        expect(modal._inside).toBe(true);
    });
});

describe('SearchModal Inside tab announcement', () => {
    const onTab = ({ hits = [], loading = false, searchKey = 'q=white+whale' } = {}) => {
        const modal = modalSetup();
        modal._mode = 'inside';
        modal._ftHits = hits;
        modal._ftLoading = loading;
        modal._ftSearchKey = searchKey;
        return modal;
    };

    test('counts the passages on screen', () => {
        expect(onTab({ hits: [{ ia: 'a' }, { ia: 'b' }] })._resultsAnnouncement())
            .toBe('2 matches found inside books');
    });

    test('a settled empty search says so', () => {
        expect(onTab()._resultsAnnouncement()).toBe('No matches inside books');
    });

    test('stays quiet while the search is in flight', () => {
        expect(onTab({ loading: true })._resultsAnnouncement()).toBe('');
    });

    // A null key means nothing has been fetched for this query yet, so "no
    // matches" would be a claim the modal hasn't earned.
    test('stays quiet before the first fetch', () => {
        expect(onTab({ searchKey: null })._resultsAnnouncement()).toBe('');
    });
});

describe('SearchModal band outcome on the Inside tab', () => {
    test('the band metric stays on the Books tab, where the catalog fetch is', () => {
        const modal = modalSetup();
        const schedule = vi.spyOn(modal, '_scheduleOutcomeTrack');
        modal._selectMode('inside');

        modal._scheduleBandOutcome('resolved');

        expect(schedule).not.toHaveBeenCalled();
    });

    test('and still fires on Books', () => {
        const modal = modalSetup();
        const schedule = vi.spyOn(modal, '_scheduleOutcomeTrack');

        modal._scheduleBandOutcome('resolved');

        expect(schedule).toHaveBeenCalledWith('FulltextBand', modal._activeFetchKey, expect.any(Function));
    });
});
