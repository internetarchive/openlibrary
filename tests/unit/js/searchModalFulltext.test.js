import {
    fulltextHitDisplay,
    parseSnippet,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/fulltext';

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
            page: 214,
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
            page: 214,
            coverUrl: null,
        });
    });

    test('returns null without an identifier or snippet', () => {
        expect(fulltextHitDisplay({ fields: {}, highlight: { text: ['x'] } })).toBeNull();
        expect(fulltextHitDisplay({ fields: { identifier: ['id'] }, highlight: { text: [] } })).toBeNull();
        expect(fulltextHitDisplay(undefined)).toBeNull();
    });

    test('tolerates a flat page_num list', () => {
        const flat = { ...hit, fields: { ...hit.fields, page_num: [31, 88] } };
        expect(fulltextHitDisplay(flat).page).toBe(31);
    });
});
