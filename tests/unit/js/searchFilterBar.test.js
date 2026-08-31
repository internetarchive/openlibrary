import { selectionFor } from '../../../openlibrary/plugins/openlibrary/js/SearchFilterBar';

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
