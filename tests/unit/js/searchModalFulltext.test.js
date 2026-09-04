import {
    creatorsFromMeta,
    dedupeFulltextHits,
    fulltextHitDisplay,
    isPassageQuery,
    parseSnippet,
    phraseQuery,
    solrLooksWeak,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/fulltext';
import { fulltextSearchParams } from '../../../openlibrary/plugins/openlibrary/js/search-modal/fulltextBand';
import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal';

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
            meta_year: [2001],
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
            year: '2001',
            snippet: 'But {{{Lokesh}}} had never seemed',
            coverUrl: 'https://covers.openlibrary.org/b/id/1-M.jpg',
            coverSrcset: '',
        });
    });

    test('falls back to scan metadata when no OL edition matched', () => {
        const bare = { ...hit, edition: undefined, fields: { ...hit.fields, meta_creator: ['Pattison, Eliot'] } };
        expect(fulltextHitDisplay(bare)).toEqual({
            ia: 'watertouchingst00patt',
            title: 'Water touching stone',
            author: 'Pattison, Eliot',
            year: '2001',
            snippet: 'But {{{Lokesh}}} had never seemed',
            coverUrl: 'https://archive.org/download/watertouchingst00patt/page/cover_w116_h58.jpg',
            coverSrcset: 'https://archive.org/download/watertouchingst00patt/page/cover_w180_h360.jpg 2x',
        });
    });

    test('no edition and no meta_creator leaves the author empty', () => {
        expect(fulltextHitDisplay({ ...hit, edition: undefined }).author).toBe('');
    });

    test('no meta_year leaves the year empty', () => {
        expect(fulltextHitDisplay({ ...hit, fields: { ...hit.fields, meta_year: undefined } }).year).toBe('');
    });
});

describe('creatorsFromMeta', () => {
    test('keeps a catalogue-style "Last, First" name whole', () => {
        expect(creatorsFromMeta(['Tyler, Denise'])).toBe('Tyler, Denise');
    });

    test('splits a packed multi-author value on bare commas and caps at three', () => {
        expect(creatorsFromMeta(['John Ganci,Oscar Aranda Crespo,Nevine Helmy,Mark Ho']))
            .toBe('John Ganci, Oscar Aranda Crespo, Nevine Helmy');
    });

    test('drops a trailing MARC relator term but keeps the name', () => {
        expect(creatorsFromMeta(['Eyre, Richard M., author'])).toBe('Eyre, Richard M.');
        expect(creatorsFromMeta(['Smith, Jane, editor.'])).toBe('Smith, Jane');
        expect(creatorsFromMeta(['Doe, John, joint author'])).toBe('Doe, John');
        expect(creatorsFromMeta(['Roe, Ann, ed., tr.'])).toBe('Roe, Ann');
        // A packed list keeps every name; only the role goes.
        expect(creatorsFromMeta(['A One, author,B Two, illustrator'])).toBe('A One, B Two');
        // Names that merely contain a role word are untouched.
        expect(creatorsFromMeta(['Author, Ann', 'Illustrated Press'])).toBe('Author, Ann, Illustrated Press');
    });

    test('joins separate values and drops blanks', () => {
        expect(creatorsFromMeta(['Ada Lovelace', '', 'Charles Babbage'])).toBe('Ada Lovelace, Charles Babbage');
        expect(creatorsFromMeta('Solo Author')).toBe('Solo Author');
        expect(creatorsFromMeta(undefined)).toBe('');
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

    test('a question mark alone is not a passage — short ones are titles', () => {
        expect(isPassageQuery('who coined meritocracy?')).toBe(false);
        expect(isPassageQuery('where\'s waldo?')).toBe(false);
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

    test('a pluralized query still matches the singular title', () => {
        expect(solrLooksWeak([{ title: 'The Hobbit', author_name: ['J.R.R. Tolkien'] }], 'hobbits')).toBe(false);
    });

    test('reverse prefixes only count for meaningful doc words', () => {
        // "The Room"'s "the" is a prefix of "theodore", but a stopword is not
        // evidence the query was answered.
        expect(solrLooksWeak([{ title: 'The Room' }], 'theodore roosevelt')).toBe(true);
    });

    test('a subtitle match is not weak', () => {
        expect(solrLooksWeak([{ title: 'Walden', subtitle: 'or, Life in the Woods' }], 'life in the woods')).toBe(false);
    });

    test('the promoted edition title counts — the modal renders that row', () => {
        const potter = {
            title: 'Harry Potter and the Chamber of Secrets',
            author_name: ['J. K. Rowling'],
            editions: { docs: [{ title: 'Harry Potter und die Kammer des Schreckens' }] },
        };
        expect(solrLooksWeak([potter], 'kammer')).toBe(false);
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

    // The case that used to justify treating "?" as a passage signal: prod Solr
    // answers it with one unrelated book, so the weak path already rescues it.
    test('a question Solr answers badly is weak', () => {
        expect(solrLooksWeak([{ title: 'The Human Planet' }], 'who coined meritocracy?')).toBe(true);
    });

    test('a question-shaped title is answered, not weak', () => {
        expect(solrLooksWeak([{ title: 'Where\'s Waldo?', author_name: ['Martin Handford'] }], 'where\'s waldo?')).toBe(false);
    });

    test('an interrogative overlapping a how-to title is not an answer', () => {
        expect(solrLooksWeak([{ title: 'How to Cook Everything' }], 'how do birds navigate?')).toBe(true);
    });

    test('only the top docs are scanned', () => {
        const filler = { title: 'Unrelated', author_name: ['Nobody'] };
        expect(solrLooksWeak([filler, filler, filler, gatsby], 'gatsby')).toBe(true);
    });
});

// Mirror of core/fulltext.py phrase_query — same cases as its Python tests.
describe('phraseQuery', () => {
    test('wraps bare words into one quoted phrase', () => {
        expect(phraseQuery('it was the best of times')).toBe('"it was the best of times"');
        expect(phraseQuery('whale')).toBe('"whale"');
    });

    test('leaves a well-formed phrase unchanged', () => {
        expect(phraseQuery('"it was the best of times"')).toBe('"it was the best of times"');
    });

    test('normalizes curly quotes, wrapping or inner', () => {
        expect(phraseQuery('\u201cit was the best of times\u201d')).toBe('"it was the best of times"');
        expect(phraseQuery('he said \u201chello there\u201d softly')).toBe('"he said hello there softly"');
    });

    test('repairs unbalanced quotes', () => {
        expect(phraseQuery('"it was the best of times')).toBe('"it was the best of times"');
        expect(phraseQuery('hello there" softly')).toBe('"hello there softly"');
    });

    test('inner quotes are removed, not escaped', () => {
        expect(phraseQuery('he said "hello there" softly')).toBe('"he said hello there softly"');
    });

    test('whitespace collapses and an emptied query yields nothing', () => {
        expect(phraseQuery('  a\n  b  ')).toBe('"a b"');
        expect(phraseQuery('  "  "  ')).toBe('');
        expect(phraseQuery('')).toBe('');
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

describe('see-all button labels', () => {
    test('the visible label is the short form, total formatted for the locale', () => {
        const modal = new SearchModal();
        modal._ftTotal = 134731;
        expect(modal._seeAllInsideShortLabel()).toBe('Search Inside 134,731 books');
    });

    test('the accessible name spells out the full sentence', () => {
        const modal = new SearchModal();
        modal._ftTotal = 134731;
        expect(modal._seeAllInsideLabel()).toBe('See all matches found in 134,731 books');
    });
});

describe('fulltext see-all freshness', () => {
    const modalFor = (query, searchKey, total = 134731) => {
        const modal = new SearchModal();
        modal._query = query;
        modal._languages = [];
        modal._ftTotal = total;
        modal._ftSearchKey = searchKey;
        return modal;
    };

    test('the count holds while the total describes the search the button links to', () => {
        expect(modalFor('white whale', 'q=white+whale')._ftTotalIsCurrent()).toBe(true);
    });

    // The band's hits linger through an edit so it doesn't flicker per keystroke.
    // The total must not: it would pair a count nobody measured for this query
    // with a link that carries the edited one.
    test('an edit drops the count', () => {
        expect(modalFor('white whales', 'q=white+whale')._ftTotalIsCurrent()).toBe(false);
    });

    test('a filter toggle drops it too — same query, different search', () => {
        const modal = modalFor('white whale', 'q=white+whale');
        modal._availability = 'readable';
        expect(modal._ftTotalIsCurrent()).toBe(false);
    });

    test('a cleared band has no count to show', () => {
        expect(modalFor('white whale', null, null)._ftTotalIsCurrent()).toBe(false);
    });

    // A total that's already fully on screen still counts as current — it's
    // _renderFulltextSeeAll that drops the redundant number, keeping the button.
    test('a fully-shown total is still current', () => {
        expect(modalFor('white whale', 'q=white+whale', 2)._ftTotalIsCurrent()).toBe(true);
    });
});

describe('catalog see-all labels', () => {
    // The there's-more case is the only one with a distinct narrow form; the
    // rest are short enough to stand as they are.
    test('offers a shorter form when there are more results than rows shown', () => {
        const modal = new SearchModal();
        modal._hasSearched = true;
        modal._numFound = 1204;
        modal._results = new Array(7).fill({});
        expect(modal._seeAllLabels()).toEqual({ wide: 'See all 1,204 books', narrow: 'All 1.2K books' });
    });

    test('reuses one label for the all-shown cases', () => {
        const modal = new SearchModal();
        modal._hasSearched = true;
        modal._numFound = 1;
        modal._results = [{}];
        expect(modal._seeAllLabels()).toEqual({ wide: 'See 1 book', narrow: 'See 1 book' });
    });

    test('sends the patron to full search when nothing matched', () => {
        const modal = new SearchModal();
        modal._hasSearched = true;
        modal._numFound = 0;
        modal._results = [];
        expect(modal._seeAllLabels()).toEqual({ wide: 'Go to full search', narrow: 'Go to full search' });
    });
});

describe('dedupeFulltextHits', () => {
    const hits = [{ ia: 'scanA' }, { ia: 'scanB' }, { ia: 'scanC' }];

    test('drops a hit whose scan is in a listed work\'s ia', () => {
        const docs = [{ ia: ['scanB', 'other'] }];
        expect(dedupeFulltextHits(hits, docs).map((h) => h.ia)).toEqual(['scanA', 'scanC']);
    });

    test('drops a hit listed only via a promoted edition', () => {
        const docs = [{ editions: { docs: [{ ia: ['scanC'] }] } }];
        expect(dedupeFulltextHits(hits, docs).map((h) => h.ia)).toEqual(['scanA', 'scanB']);
    });

    test('keeps every hit when nothing overlaps, order intact', () => {
        const docs = [{ ia: ['unrelated'] }, { key: '/works/OL1W' }];
        expect(dedupeFulltextHits(hits, docs)).toEqual(hits);
    });

    test('no docs — the rescue path — filters nothing', () => {
        expect(dedupeFulltextHits(hits, [])).toEqual(hits);
        expect(dedupeFulltextHits(hits, undefined)).toEqual(hits);
    });
});
