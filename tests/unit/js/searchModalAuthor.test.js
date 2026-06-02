import {
    AUTHOR_SUGGESTION_MAX,
    deriveAuthors,
    queryMatchesName,
} from '../../../openlibrary/plugins/openlibrary/js/search-modal/authorSuggestion';

/** Build a /search.json-style work doc with a single primary author. */
function work(key, authorName, authorKey) {
    return {
        key,
        title: `Work ${key}`,
        author_name: authorName ? [authorName] : undefined,
        author_key: authorKey ? [authorKey] : undefined,
    };
}

describe('queryMatchesName', () => {
    test('matches a surname substring of the full name', () => {
        expect(queryMatchesName('asimov', 'Isaac Asimov')).toBe(true);
    });

    test('matches the full name typed out', () => {
        expect(queryMatchesName('octavia butler', 'Octavia E. Butler')).toBe(true);
    });

    test('matches on a shared whole word', () => {
        expect(queryMatchesName('le guin', 'Ursula K. Le Guin')).toBe(true);
    });

    test('does not match a title that happens to skew to one author', () => {
        expect(queryMatchesName('dune', 'Frank Herbert')).toBe(false);
        expect(queryMatchesName('the great gatsby', 'F. Scott Fitzgerald')).toBe(false);
    });

    test('ignores short shared tokens like particles/initials', () => {
        expect(queryMatchesName('the de la', 'Walter de la Mare')).toBe(false);
    });

    test('folds diacritics', () => {
        expect(queryMatchesName('gabriel garcia marquez', 'Gabriel García Márquez')).toBe(true);
    });

    test('is empty-safe', () => {
        expect(queryMatchesName('', 'Isaac Asimov')).toBe(false);
        expect(queryMatchesName('asimov', '')).toBe(false);
        expect(queryMatchesName(undefined, undefined)).toBe(false);
    });
});

describe('deriveAuthors', () => {
    test('surfaces a named author even with a single book in the results', () => {
        const docs = [
            work('/works/OL1W', 'Octavia E. Butler', 'OL11A'),
            work('/works/OL2W', 'Someone Else', 'OL22A'),
        ];
        expect(deriveAuthors(docs, 'octavia butler')).toEqual([{ key: 'OL11A', name: 'Octavia E. Butler' }]);
    });

    test('surfaces multiple distinct authors for an ambiguous given name', () => {
        const docs = [
            work('/works/OL1W', 'Stephen King', 'OL19A'),
            work('/works/OL2W', 'Stephen Hawking', 'OL20A'),
            work('/works/OL3W', 'Stephen King', 'OL19A'), // dupe key → collapsed
        ];
        expect(deriveAuthors(docs, 'stephen')).toEqual([
            { key: 'OL19A', name: 'Stephen King' },
            { key: 'OL20A', name: 'Stephen Hawking' },
        ]);
    });

    test('dedupes a prolific author to a single row', () => {
        const docs = Array.from({ length: 4 }, (_, i) => work(`/works/OL${i}W`, 'Isaac Asimov', 'OL34221A'));
        expect(deriveAuthors(docs, 'asimov')).toEqual([{ key: 'OL34221A', name: 'Isaac Asimov' }]);
    });

    test(`caps the number of author rows at ${AUTHOR_SUGGESTION_MAX}`, () => {
        const docs = [
            work('/works/OL1W', 'John Smith', 'OL1A'),
            work('/works/OL2W', 'Jane Smith', 'OL2A'),
            work('/works/OL3W', 'Adam Smith', 'OL3A'),
            work('/works/OL4W', 'Zadie Smith', 'OL4A'),
        ];
        expect(deriveAuthors(docs, 'smith')).toHaveLength(AUTHOR_SUGGESTION_MAX);
    });

    test('only scans the top results, not the whole page', () => {
        // Asimov is the 6th result — past the scan window — so no row.
        const docs = [
            ...Array.from({ length: 5 }, (_, i) => work(`/works/OL${i}W`, 'Filler Writer', `OL9${i}A`)),
            work('/works/OLaW', 'Isaac Asimov', 'OL34221A'),
        ];
        expect(deriveAuthors(docs, 'asimov')).toEqual([]);
    });

    test('returns nothing for a title search even when results skew to one author', () => {
        const docs = Array.from({ length: 5 }, (_, i) => work(`/works/OL${i}W`, 'Frank Herbert', 'OL79034A'));
        expect(deriveAuthors(docs, 'dune')).toEqual([]);
    });

    test('ignores docs missing an author key (can not link to a page)', () => {
        const docs = [work('/works/OL1W', 'Isaac Asimov', undefined)];
        expect(deriveAuthors(docs, 'asimov')).toEqual([]);
    });

    test('is empty-safe', () => {
        expect(deriveAuthors([], 'asimov')).toEqual([]);
        expect(deriveAuthors(null, 'asimov')).toEqual([]);
    });
});
