import {
    languageOptionsWithCounts,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/languages';

const options = [
    { value: 'eng', label: 'English' },
    { value: 'fre', label: 'French' },
    { value: 'ger', label: 'German' },
    { value: 'spa', label: 'Spanish' },
];

describe('languageOptionsWithCounts', () => {
    test('returns uncounted options before facets are available', () => {
        expect(languageOptionsWithCounts(options, null)).toEqual(options);
    });

    test('adds counts and sorts counted languages by highest count', () => {
        expect(languageOptionsWithCounts(options, [
            ['fre', 'French', 12],
            ['eng', 'English', 40],
            ['spa', 'Spanish', 4],
        ])).toEqual([
            { value: 'eng', label: 'English', count: '40' },
            { value: 'fre', label: 'French', count: '12' },
            { value: 'spa', label: 'Spanish', count: '4' },
        ]);
    });

    test('keeps selected languages visible even when they have no facet count', () => {
        expect(languageOptionsWithCounts(options, [
            ['eng', 'English', 40],
        ], ['ger'])).toEqual([
            { value: 'ger', label: 'German', count: '0' },
            { value: 'eng', label: 'English', count: '40' },
        ]);
    });
});
