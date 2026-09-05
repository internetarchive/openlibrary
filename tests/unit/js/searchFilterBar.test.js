import {
    SURFACES,
    selectionFor,
    stickyFilterParams,
    syncSessionStorageFromUrl,
} from '../../../openlibrary/plugins/openlibrary/js/SearchFilterBar';
import {
    SS_AVAILABILITY_KEY,
    SS_LANGUAGES_KEY,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/constants';

const MULTI = { singleLanguage: false };
const SINGLE = { singleLanguage: true };

describe('selectionFor', () => {
    test('leaves a multi-select surface untouched', () => {
        expect(selectionFor(MULTI, ['fre', 'ger'], 'ger')).toEqual(['fre', 'ger']);
    });

    test('keeps only the language just picked on a single-select surface', () => {
        // /search/inside: the FTS `lang` param takes one value, so a second
        // pick replaces the first rather than adding to it.
        expect(selectionFor(SINGLE, ['fre', 'ger'], 'ger')).toEqual(['ger']);
    });

    test('deselecting clears the filter rather than reviving the old value', () => {
        expect(selectionFor(SINGLE, [], null)).toEqual([]);
    });

    test('truncates a seeded selection from a hand-edited URL', () => {
        // No `added` here — this is init reading ?language=fre&language=ger.
        expect(selectionFor(SINGLE, ['fre', 'ger'])).toEqual(['fre']);
    });

    test('a single selection passes through unchanged', () => {
        expect(selectionFor(SINGLE, ['fre'], 'fre')).toEqual(['fre']);
    });
});

describe('sticky filter round-trip', () => {
    const CATALOG = SURFACES['/search'];
    const INSIDE = SURFACES['/search/inside'];

    const store = (availability, languages) => {
        sessionStorage.setItem(SS_AVAILABILITY_KEY, availability);
        sessionStorage.setItem(SS_LANGUAGES_KEY, JSON.stringify(languages));
    };
    const storedAvailability = () => sessionStorage.getItem(SS_AVAILABILITY_KEY);
    const storedLanguages = () => JSON.parse(sessionStorage.getItem(SS_LANGUAGES_KEY));
    const q = (search) => new URLSearchParams(search);

    beforeEach(() => {
        sessionStorage.clear();
    });

    describe('syncSessionStorageFromUrl', () => {
        test('/search/inside keeps an availability its URL cannot express', () => {
            // The regression this guards: readable=true is the only availability
            // /search/inside can write, so reading it back as 'readable' would
            // broaden a "Free to read now" pick the patron never touched.
            store('open', []);
            syncSessionStorageFromUrl(INSIDE, q('q=dracula&readable=true'));
            expect(storedAvailability()).toBe('open');
        });

        test('/search/inside still records the toggle being turned off', () => {
            store('open', []);
            syncSessionStorageFromUrl(INSIDE, q('q=dracula'));
            expect(storedAvailability()).toBe('all');
        });

        test('/search records a genuine availability change', () => {
            store('open', []);
            syncSessionStorageFromUrl(CATALOG, q('q=dracula&has_fulltext=true'));
            expect(storedAvailability()).toBe('readable');
        });

        test('/search leaves an availability that round-trips alone', () => {
            store('open', []);
            syncSessionStorageFromUrl(CATALOG, q('q=dracula&public_scan=true'));
            expect(storedAvailability()).toBe('open');
        });

        test('/search/inside keeps the language its URL had to drop', () => {
            store('all', ['eng', 'fre']);
            syncSessionStorageFromUrl(INSIDE, q('q=whale&language=eng'));
            expect(storedLanguages()).toEqual(['eng', 'fre']);
        });

        test('/search/inside records a language actually picked there', () => {
            store('all', ['eng', 'fre']);
            syncSessionStorageFromUrl(INSIDE, q('q=whale&language=ger'));
            expect(storedLanguages()).toEqual(['ger']);
        });

        test('/search mirrors the sidebar language facet', () => {
            store('all', ['eng']);
            syncSessionStorageFromUrl(CATALOG, q('q=whale&language=fre'));
            expect(storedLanguages()).toEqual(['fre']);
        });

        test('clearing every filter clears both stored values', () => {
            store('readable', ['eng']);
            syncSessionStorageFromUrl(CATALOG, q('q=whale'));
            expect(storedAvailability()).toBe('all');
            expect(storedLanguages()).toEqual([]);
        });
    });

    describe('stickyFilterParams', () => {
        test('/search/inside applies only the language it can honor', () => {
            store('all', ['eng', 'fre']);
            expect(stickyFilterParams(INSIDE, q('q=whale')).getAll('language')).toEqual(['eng']);
        });

        test('/search applies every stored language', () => {
            store('all', ['eng', 'fre']);
            expect(stickyFilterParams(CATALOG, q('q=whale')).getAll('language')).toEqual(['eng', 'fre']);
        });

        test('/search/inside collapses a finer availability onto readable', () => {
            store('open', []);
            expect(stickyFilterParams(INSIDE, q('q=whale')).get('readable')).toBe('true');
        });

        test('stands aside when the URL already carries a filter', () => {
            store('readable', []);
            expect(stickyFilterParams(CATALOG, q('q=whale&has_fulltext=true'))).toBeNull();
        });

        test('stands aside when nothing non-default is stored', () => {
            store('all', []);
            expect(stickyFilterParams(CATALOG, q('q=whale'))).toBeNull();
        });
    });

    test('a pass through /search/inside leaves the /search filters intact', () => {
        store('open', ['eng', 'fre']);
        // Both init steps, in the order a page load runs them: sticky filters
        // rewrite the bare URL, then that URL is mirrored back to storage.
        syncSessionStorageFromUrl(INSIDE, stickyFilterParams(INSIDE, q('q=dracula')));
        expect(storedAvailability()).toBe('open');
        expect(storedLanguages()).toEqual(['eng', 'fre']);
    });
});
