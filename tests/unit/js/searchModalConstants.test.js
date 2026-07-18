import {
    AVAILABILITY_OPTIONS,
    DEFAULT_AVAILABILITY,
    DEFAULT_SEARCH_MODAL_STRINGS,
    LS_AVAILABILITY_KEY,
    LS_LANGUAGES_KEY,
    LS_RECENT_SEARCHES_KEY,
    RECENT_SEARCHES_MAX,
    availabilityFromParams,
    availabilityOptionsFromElement,
    languageNameFromOptions,
    localizeAvailabilityOptions,
    readRecentSearches,
    readStoredAvailability,
    readStoredLanguages,
    readableEditionLanguages,
    readableLanguageMismatch,
    removeRecentSearch,
    saveRecentSearch,
    searchModalStringsFromElement,
    siteLanguageToMarc,
    writeStoredAvailability,
    writeStoredLanguages,
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
        expect(DEFAULT_SEARCH_MODAL_STRINGS.seeAll).toBe('See results');
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

describe('siteLanguageToMarc', () => {
    test('maps a UI language to its MARC bibliographic code', () => {
        expect(siteLanguageToMarc('en')).toBe('eng');
        expect(siteLanguageToMarc('fr')).toBe('fre');
    });

    test('uses the bibliographic (not terminology) code for the MARC quirks', () => {
        expect(siteLanguageToMarc('de')).toBe('ger'); // not deu
        expect(siteLanguageToMarc('zh')).toBe('chi'); // not zho
        expect(siteLanguageToMarc('cs')).toBe('cze'); // not ces
    });

    test('returns "" for an unknown or empty code', () => {
        expect(siteLanguageToMarc('ja')).toBe(''); // not a switcher UI language
        expect(siteLanguageToMarc('')).toBe('');
    });
});

describe('languageNameFromOptions', () => {
    const opts = [{ value: 'fre', label: 'Français' }, { value: 'eng', label: 'English' }];

    test('returns the matching label', () => {
        expect(languageNameFromOptions(opts, 'fre')).toBe('Français');
    });

    test('returns null for an unknown code', () => {
        expect(languageNameFromOptions(opts, 'zzz')).toBeNull();
    });

    test('falls back to the built-in defaults when options are empty', () => {
        // DEFAULT_LANGUAGE_OPTIONS carries the English fallback name for 'fre'.
        expect(languageNameFromOptions([], 'fre')).toBe('French');
        expect(languageNameFromOptions(null, 'eng')).toBe('English');
    });
});

describe('readableLanguageMismatch', () => {
    const opts = [
        { value: 'fre', label: 'French' },
        { value: 'ger', label: 'German' },
        { value: 'spa', label: 'Spanish' },
        { value: 'eng', label: 'English' },
    ];
    const base = {
        edition: { language: ['fre'] },
        languages: [],
        siteLanguage: 'eng',
        options: opts,
    };

    test('returns the localized name when the readable edition is in another language', () => {
        expect(readableLanguageMismatch(base)).toBe('French');
    });

    test('names two languages joined with a comma, no ellipsis', () => {
        expect(readableLanguageMismatch({ ...base, edition: { language: ['fre', 'ger'] } })).toBe('French, German');
    });

    test('names the first two and appends an ellipsis when the edition lists more', () => {
        expect(readableLanguageMismatch({ ...base, edition: { language: ['fre', 'ger', 'spa'] } })).toBe('French, German, …');
    });

    test('drops codes with no display name before counting (no wasted slot, no ellipsis)', () => {
        expect(readableLanguageMismatch({ ...base, edition: { language: ['fre', 'zzz'] } })).toBe('French');
    });

    test('returns null when the edition is already in the site language', () => {
        expect(readableLanguageMismatch({ ...base, edition: { language: ['eng'] } })).toBeNull();
    });

    test('returns null when the edition lists the site language among others', () => {
        expect(readableLanguageMismatch({ ...base, edition: { language: ['eng', 'fre'] } })).toBeNull();
    });

    test('returns null when there is no promoted readable edition', () => {
        expect(readableLanguageMismatch({ ...base, edition: null })).toBeNull();
    });

    test('returns null when the patron already chose a language filter', () => {
        expect(readableLanguageMismatch({ ...base, languages: ['fre'] })).toBeNull();
    });

    test('returns null when the site language is unknown', () => {
        expect(readableLanguageMismatch({ ...base, siteLanguage: '' })).toBeNull();
    });

    test('returns null when the edition carries no language', () => {
        expect(readableLanguageMismatch({ ...base, edition: {} })).toBeNull();
        expect(readableLanguageMismatch({ ...base, edition: { language: [] } })).toBeNull();
    });

    test('returns null when the mismatched code has no display name', () => {
        expect(readableLanguageMismatch({ ...base, edition: { language: ['zzz'] }, options: [] })).toBeNull();
    });
});

describe('recent searches (localStorage)', () => {
    beforeEach(() => {
        localStorage.clear();
        jest.restoreAllMocks();
    });

    describe('readRecentSearches', () => {
        test('returns [] when nothing is stored', () => {
            expect(readRecentSearches()).toEqual([]);
        });

        test('returns the stored list, capped at RECENT_SEARCHES_MAX', () => {
            const stored = Array.from({ length: RECENT_SEARCHES_MAX + 3 }, (_, i) => `q${i}`);
            localStorage.setItem(LS_RECENT_SEARCHES_KEY, JSON.stringify(stored));
            expect(readRecentSearches()).toEqual(stored.slice(0, RECENT_SEARCHES_MAX));
        });

        test('returns [] on unparseable JSON', () => {
            localStorage.setItem(LS_RECENT_SEARCHES_KEY, '{not json');
            expect(readRecentSearches()).toEqual([]);
        });

        test('returns [] when the parsed value is not an array', () => {
            localStorage.setItem(LS_RECENT_SEARCHES_KEY, JSON.stringify({ a: 1 }));
            expect(readRecentSearches()).toEqual([]);
        });

        test('drops non-string entries from a corrupt value', () => {
            localStorage.setItem(LS_RECENT_SEARCHES_KEY, JSON.stringify(['dogs', null, { x: 1 }, 'cats', 42]));
            expect(readRecentSearches()).toEqual(['dogs', 'cats']);
        });

        test('returns [] when localStorage.getItem throws (private browsing)', () => {
            jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
            expect(readRecentSearches()).toEqual([]);
        });
    });

    describe('saveRecentSearch', () => {
        test('prepends, deduplicates to the front, and caps the list', () => {
            saveRecentSearch('alpha');
            saveRecentSearch('beta');
            saveRecentSearch('alpha'); // moves to front, no duplicate
            expect(readRecentSearches()).toEqual(['alpha', 'beta']);
        });

        test('ignores blank / whitespace-only queries and trims', () => {
            saveRecentSearch('   ');
            saveRecentSearch('  spaced  ');
            expect(readRecentSearches()).toEqual(['spaced']);
        });

        test('never grows past RECENT_SEARCHES_MAX', () => {
            for (let i = 0; i < RECENT_SEARCHES_MAX + 5; i++) saveRecentSearch(`q${i}`);
            const list = readRecentSearches();
            expect(list).toHaveLength(RECENT_SEARCHES_MAX);
            // Most recent first.
            expect(list[0]).toBe(`q${RECENT_SEARCHES_MAX + 4}`);
        });

        test('silently ignores a setItem failure (quota / private browsing)', () => {
            jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
            expect(() => saveRecentSearch('whatever')).not.toThrow();
        });
    });

    describe('removeRecentSearch', () => {
        test('removes a single entry and returns the updated list', () => {
            saveRecentSearch('one');
            saveRecentSearch('two');
            saveRecentSearch('three');
            expect(removeRecentSearch('two')).toEqual(['three', 'one']);
            expect(readRecentSearches()).toEqual(['three', 'one']);
        });

        test('is a no-op for a value that is not present', () => {
            saveRecentSearch('only');
            expect(removeRecentSearch('absent')).toEqual(['only']);
        });
    });
});

describe('readStoredLanguages (localStorage)', () => {
    beforeEach(() => {
        localStorage.clear();
        jest.restoreAllMocks();
    });

    test('returns [] when nothing is stored', () => {
        expect(readStoredLanguages()).toEqual([]);
    });

    test('returns the stored array of codes', () => {
        localStorage.setItem(LS_LANGUAGES_KEY, JSON.stringify(['eng', 'fre']));
        expect(readStoredLanguages()).toEqual(['eng', 'fre']);
    });

    test('returns [] when the parsed value is not an array', () => {
        localStorage.setItem(LS_LANGUAGES_KEY, JSON.stringify('eng'));
        expect(readStoredLanguages()).toEqual([]);
    });

    test('drops non-string entries so a corrupt value cannot leak a bogus filter', () => {
        localStorage.setItem(LS_LANGUAGES_KEY, JSON.stringify(['eng', 1, null, 'spa']));
        expect(readStoredLanguages()).toEqual(['eng', 'spa']);
    });

    test('returns [] on unparseable JSON', () => {
        localStorage.setItem(LS_LANGUAGES_KEY, '{nope');
        expect(readStoredLanguages()).toEqual([]);
    });

    test('returns [] when localStorage.getItem throws (private browsing)', () => {
        jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
        expect(readStoredLanguages()).toEqual([]);
    });
});

describe('availability/language preference round-trip (localStorage)', () => {
    beforeEach(() => {
        localStorage.clear();
        jest.restoreAllMocks();
    });

    test('readStoredAvailability falls back to the default when unset', () => {
        expect(readStoredAvailability()).toBe(DEFAULT_AVAILABILITY);
    });

    test('writeStoredAvailability round-trips a value', () => {
        writeStoredAvailability('readable');
        expect(localStorage.getItem(LS_AVAILABILITY_KEY)).toBe('readable');
        expect(readStoredAvailability()).toBe('readable');
    });

    test('writeStoredAvailability coerces a falsy value to the default', () => {
        writeStoredAvailability('');
        expect(localStorage.getItem(LS_AVAILABILITY_KEY)).toBe(DEFAULT_AVAILABILITY);
    });

    test('writeStoredLanguages round-trips through readStoredLanguages', () => {
        writeStoredLanguages(['eng', 'fre']);
        expect(localStorage.getItem(LS_LANGUAGES_KEY)).toBe(JSON.stringify(['eng', 'fre']));
        expect(readStoredLanguages()).toEqual(['eng', 'fre']);
    });

    test('writeStoredLanguages treats a nullish list as empty', () => {
        writeStoredLanguages(null);
        expect(readStoredLanguages()).toEqual([]);
    });

    test('the preference persists across a simulated session boundary', () => {
        // localStorage (not sessionStorage) is what makes availability + language
        // durable across visits — the whole point of the Phase 0 migration.
        writeStoredAvailability('readable');
        writeStoredLanguages(['spa']);
        // A new page load reads the same backing store; nothing is cleared.
        expect(readStoredAvailability()).toBe('readable');
        expect(readStoredLanguages()).toEqual(['spa']);
    });

    test('write helpers are no-ops when localStorage.setItem throws', () => {
        jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied'); });
        expect(() => writeStoredAvailability('readable')).not.toThrow();
        expect(() => writeStoredLanguages(['eng'])).not.toThrow();
    });
});

describe('readableEditionLanguages', () => {
    const opts = [
        { value: 'fre', label: 'French' },
        { value: 'ger', label: 'German' },
        { value: 'spa', label: 'Spanish' },
        { value: 'eng', label: 'English' },
    ];
    const base = {
        edition: { language: ['fre'] },
        languages: ['eng', 'fre'],
        options: opts,
    };

    test('names the readable copy\'s language when several languages are selected', () => {
        expect(readableEditionLanguages(base)).toBe('French');
    });

    test('names the language even when it matches the patron\'s site language choice', () => {
        // No site-language gating here: the explicit filter overrides it.
        expect(readableEditionLanguages({ ...base, edition: { language: ['eng'] } })).toBe('English');
    });

    test('names two languages joined with a comma, no ellipsis', () => {
        expect(readableEditionLanguages({ ...base, edition: { language: ['fre', 'ger'] } })).toBe('French, German');
    });

    test('names the first two and appends an ellipsis when the edition lists more', () => {
        expect(readableEditionLanguages({ ...base, edition: { language: ['fre', 'ger', 'spa'] } })).toBe('French, German, …');
    });

    test('drops codes with no display name before counting', () => {
        expect(readableEditionLanguages({ ...base, edition: { language: ['fre', 'zzz'] } })).toBe('French');
    });

    test('returns null when fewer than two languages are selected', () => {
        expect(readableEditionLanguages({ ...base, languages: ['fre'] })).toBeNull();
        expect(readableEditionLanguages({ ...base, languages: [] })).toBeNull();
    });

    test('returns null when there is no promoted readable edition', () => {
        expect(readableEditionLanguages({ ...base, edition: null })).toBeNull();
    });

    test('returns null when the edition carries no language', () => {
        expect(readableEditionLanguages({ ...base, edition: {} })).toBeNull();
        expect(readableEditionLanguages({ ...base, edition: { language: [] } })).toBeNull();
    });

    test('returns null when no code resolves to a display name', () => {
        expect(readableEditionLanguages({ ...base, edition: { language: ['zzz'] }, options: [] })).toBeNull();
    });
});
