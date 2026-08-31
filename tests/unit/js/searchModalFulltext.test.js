import {
    fulltextHitDisplay,
    isPassageQuery,
    parseSnippet,
    solrLooksWeak,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/fulltext';
import { fulltextSearchParams } from '../../../openlibrary/plugins/openlibrary/js/search-modal/fulltextBand';

describe('parseSnippet', () => {
    test('splits text around {{{match}}} markers', () => {
        expect(parseSnippet('never came. But {{{Lokesh}}} had never')).toEqual([
            { text: 'never came. But ', match: false },
            { text: 'Lokesh', match: true },
            { text: ' had never', match: false },
        ]);
    });

    test('handles multiple matches', () => {
        expect(parseSnippet('{{{red}}} rising and {{{red}}} falling')).toEqual([
            { text: 'red', match: true },
            { text: ' rising and ', match: false },
            { text: 'red', match: true },
            { text: ' falling', match: false },
        ]);
    });

    test('plain text yields one unmatched segment', () => {
        expect(parseSnippet('no markers here')).toEqual([
            { text: 'no markers here', match: false },
        ]);
    });

    test('unbalanced trailing marker keeps the text as a match', () => {
        expect(parseSnippet('ends with {{{truncated')).toEqual([
            { text: 'ends with ', match: false },
            { text: 'truncated', match: true },
        ]);
    });

    test('empty and non-string input yield no segments', () => {
        expect(parseSnippet('')).toEqual([]);
        expect(parseSnippet(undefined)).toEqual([]);
        expect(parseSnippet(null)).toEqual([]);
    });
});

describe('fulltextHitDisplay', () => {
    const hit = {
        fields: {
            identifier: ['watertouchingst00patt'],
            meta_title: ['Water touching stone'],
            page_num: [[214]],
        },
        highlight: { text: ['But {{{Lokesh}}} had never seemed'] },
        edition: {
            key: '/books/OL1M',
            title: 'Water Touching Stone',
            authors: [{ key: '/authors/OL1A', name: 'Eliot Pattison' }],
            cover_url: 'https://covers.openlibrary.org/b/id/1-M.jpg',
        },
    };

    test('prefers the hydrated OL edition', () => {
        expect(fulltextHitDisplay(hit)).toEqual({
            ia: 'watertouchingst00patt',
            title: 'Water Touching Stone',
            author: 'Eliot Pattison',
            snippet: 'But {{{Lokesh}}} had never seemed',
            coverUrl: 'https://covers.openlibrary.org/b/id/1-M.jpg',
        });
    });

    test('falls back to scan metadata when no OL edition matched', () => {
        const bare = { ...hit, edition: undefined };
        expect(fulltextHitDisplay(bare)).toEqual({
            ia: 'watertouchingst00patt',
            title: 'Water touching stone',
            author: '',
            snippet: 'But {{{Lokesh}}} had never seemed',
            coverUrl: null,
        });
    });

    test('returns null without an identifier or snippet', () => {
        expect(fulltextHitDisplay({ fields: {}, highlight: { text: ['x'] } })).toBeNull();
        expect(fulltextHitDisplay({ fields: { identifier: ['id'] }, highlight: { text: [] } })).toBeNull();
        expect(fulltextHitDisplay(undefined)).toBeNull();
    });
});

describe('isPassageQuery', () => {
    test('quoted phrases are passages, straight or curly', () => {
        expect(isPassageQuery('"best of times"')).toBe(true);
        expect(isPassageQuery('“best of times”')).toBe(true);
    });

    test('empty quotes are not a phrase', () => {
        expect(isPassageQuery('"" dune')).toBe(false);
    });

    test('question-shaped queries are passages', () => {
        expect(isPassageQuery('who coined meritocracy?')).toBe(true);
    });

    test('long queries are passages, short ones are lookups', () => {
        expect(isPassageQuery('it was the best of times')).toBe(true);
        expect(isPassageQuery('the secret garden')).toBe(false);
        expect(isPassageQuery('dune')).toBe(false);
    });

    test('empty and non-string input are not passages', () => {
        expect(isPassageQuery('')).toBe(false);
        expect(isPassageQuery('   ')).toBe(false);
        expect(isPassageQuery(undefined)).toBe(false);
    });
});

describe('solrLooksWeak', () => {
    const gatsby = { title: 'The Great Gatsby', author_name: ['F. Scott Fitzgerald'] };

    test('no docs is weak', () => {
        expect(solrLooksWeak([], 'anything')).toBe(true);
        expect(solrLooksWeak(undefined, 'anything')).toBe(true);
    });

    test('a title match is not weak', () => {
        expect(solrLooksWeak([gatsby], 'great gatsby')).toBe(false);
    });

    test('an author match is not weak', () => {
        expect(solrLooksWeak([gatsby], 'fitzgerald')).toBe(false);
    });

    test('prefix overlap counts, diacritics folded', () => {
        expect(solrLooksWeak([gatsby], 'gats')).toBe(false);
        expect(solrLooksWeak([{ title: 'García Márquez reader' }], 'garcia')).toBe(false);
    });

    test('no overlap in the top docs is weak', () => {
        expect(solrLooksWeak([gatsby], 'hobit')).toBe(true);
    });

    test('overlap must be word-initial', () => {
        // "art" appears mid-word in "Bartleby" — that's not an answer.
        expect(solrLooksWeak([{ title: 'Bartleby the Scrivener' }], 'art')).toBe(true);
    });

    test('stopword-only queries are treated as answered', () => {
        expect(solrLooksWeak([gatsby], 'the and')).toBe(false);
    });

    test('only the top docs are scanned', () => {
        const filler = { title: 'Unrelated', author_name: ['Nobody'] };
        expect(solrLooksWeak([filler, filler, filler, gatsby], 'gatsby')).toBe(true);
    });
});

describe('fulltextSearchParams', () => {
    test('carries the query alone when no filter is set', () => {
        const params = fulltextSearchParams('white whale', { readable: false, languages: [] });
        expect(params.toString()).toBe('q=white+whale');
    });

    test('maps a non-default availability onto readable=true', () => {
        const params = fulltextSearchParams('white whale', { readable: true, languages: [] });
        expect(params.get('readable')).toBe('true');
    });

    // The FTS backend's `lang` param takes one language and the handler drops
    // the rest, so the band and its "see all" URL must not claim more.
    test('narrows the language selection to the first code', () => {
        const params = fulltextSearchParams('white whale', { readable: false, languages: ['fre', 'ger'] });
        expect(params.getAll('language')).toEqual(['fre']);
    });
});
