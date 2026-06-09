import {
    AVAILABILITY_OPTIONS,
    DEFAULT_SEARCH_MODAL_STRINGS,
    availabilityFromParams,
    availabilityOptionsFromElement,
    localizeAvailabilityOptions,
    searchModalStringsFromElement,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/constants';

describe('localizeAvailabilityOptions', () => {
    test('returns the English defaults when given no translations', () => {
        expect(localizeAvailabilityOptions(null)).toBe(AVAILABILITY_OPTIONS);
    });

    test('overrides label by option value', () => {
        const localized = localizeAvailabilityOptions({
            readable: { label: 'Lire maintenant' },
        });
        const readable = localized.find((o) => o.value === 'readable');
        expect(readable.label).toBe('Lire maintenant');
        // Untranslated values keep their English text...
        expect(localized.find((o) => o.value === 'all').label).toBe('All books');
        // ...and the non-translatable `value` is preserved.
        expect(readable.value).toBe('readable');
    });

    test('keeps the English label when a translation omits it', () => {
        const localized = localizeAvailabilityOptions({
            readable: {},
        });
        const readable = localized.find((o) => o.value === 'readable');
        expect(readable.label).toBe('Readable Only');
    });

    test('does not mutate the shared defaults', () => {
        localizeAvailabilityOptions({ all: { label: 'Tout' } });
        expect(AVAILABILITY_OPTIONS.find((o) => o.value === 'all').label).toBe('All books');
    });
});

describe('availabilityOptionsFromElement', () => {
    const elWith = (i18n) => ({ dataset: i18n === undefined ? {} : { i18n } });

    test('parses the data-i18n attribute and localizes', () => {
        const el = elWith(JSON.stringify({ open: { label: 'Aperçu' } }));
        expect(availabilityOptionsFromElement(el).find((o) => o.value === 'open').label).toBe('Aperçu');
    });

    test('falls back to defaults when the attribute is absent', () => {
        expect(availabilityOptionsFromElement(elWith())).toBe(AVAILABILITY_OPTIONS);
    });

    test('falls back to defaults on malformed JSON', () => {
        expect(availabilityOptionsFromElement(elWith('{not json'))).toBe(AVAILABILITY_OPTIONS);
    });

    test('tolerates a null element', () => {
        expect(availabilityOptionsFromElement(null)).toBe(AVAILABILITY_OPTIONS);
    });
});

describe('searchModalStringsFromElement', () => {
    const elWith = (i18nUi) => ({ dataset: i18nUi === undefined ? {} : { i18nUi } });

    test('parses data-i18n-ui and merges over the English defaults', () => {
        const el = elWith(JSON.stringify({ seeAll: 'Voir tout', noResults: 'Aucun résultat' }));
        const s = searchModalStringsFromElement(el);
        expect(s.seeAll).toBe('Voir tout');
        expect(s.noResults).toBe('Aucun résultat');
        // Untranslated keys keep their English text.
        expect(s.clearAll).toBe('Clear all');
    });

    test('preserves the %s placeholder in removeRecent', () => {
        const el = elWith(JSON.stringify({ removeRecent: 'Retirer « %s » des recherches récentes' }));
        expect(searchModalStringsFromElement(el).removeRecent).toBe('Retirer « %s » des recherches récentes');
    });

    test('falls back to the full English set when the attribute is absent', () => {
        expect(searchModalStringsFromElement(elWith())).toBe(DEFAULT_SEARCH_MODAL_STRINGS);
    });

    test('falls back to defaults on malformed JSON', () => {
        expect(searchModalStringsFromElement(elWith('{nope'))).toBe(DEFAULT_SEARCH_MODAL_STRINGS);
    });

    test('tolerates a null element', () => {
        expect(searchModalStringsFromElement(null)).toBe(DEFAULT_SEARCH_MODAL_STRINGS);
    });

    test('does not mutate the shared defaults', () => {
        searchModalStringsFromElement(elWith(JSON.stringify({ seeAll: 'X' })));
        expect(DEFAULT_SEARCH_MODAL_STRINGS.seeAll).toBe('See all results');
    });
});

describe('availabilityFromParams', () => {
    const fromObj = (obj) => availabilityFromParams((name) => obj[name]);

    test('maps params back to their availability value', () => {
        expect(fromObj({ has_fulltext: 'true' })).toBe('readable');
        expect(fromObj({ has_fulltext: 'true', public_scan: 'false' })).toBe('borrowable');
        expect(fromObj({ public_scan: 'true' })).toBe('open');
    });

    test('falls back to the default when nothing matches', () => {
        expect(fromObj({})).toBe('all');
    });
});
