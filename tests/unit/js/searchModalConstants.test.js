import {
    AVAILABILITY_OPTIONS,
    DEFAULT_SEARCH_MODAL_STRINGS,
    availabilityFromParams,
    availabilityOptionsFromElement,
    languageNameFromOptions,
    localizeAvailabilityOptions,
    readableEditionLanguages,
    readableLanguageMismatch,
    searchModalStringsFromElement,
    siteLanguageToMarc,
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
