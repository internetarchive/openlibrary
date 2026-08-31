/**
 * Helpers for the search modal's "Found inside books" band — parsing the
 * IA fulltext API's snippet markup and hit fields into renderable data.
 * Kept free of Lit/DOM so they're unit-testable.
 */

/** Word count at/above which an unquoted query reads as a passage, not a title. */
export const PASSAGE_WORD_COUNT = 5;

/** How many top Solr docs are checked for query-term overlap in solrLooksWeak. */
export const WEAK_SCAN_LIMIT = 3;

// Words too common to count as a real title/author overlap on their own.
// Interrogatives are here because questions rely on this check for their
// rescue: "how do birds navigate?" overlapping a "How to..." title is not
// evidence the question was answered.
const OVERLAP_STOPWORDS = new Set([
    'the', 'and', 'for', 'with', 'from', 'was', 'are', 'not', 'but',
    'his', 'her', 'its', 'this', 'that', 'you', 'all',
    'who', 'what', 'when', 'where', 'why', 'how',
]);

/** Lowercase and strip diacritics so "garcia" matches "García". */
function fold(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/**
 * True when the query reads like a passage rather than a title/author lookup —
 * a quoted phrase (straight or curly quotes), or PASSAGE_WORD_COUNT+ words —
 * words remembered from inside a book. A question mark is deliberately not a
 * signal: short interrogatives are usually titles ("Where's Waldo?"), and a
 * real question Solr answers badly is already caught by solrLooksWeak.
 *
 * @param {string} query
 * @returns {boolean}
 */
export function isPassageQuery(query) {
    const q = (query || '').trim();
    if (!q) return false;
    if (/"[^"]+"|“[^”]+”/.test(q)) return true;
    return q.split(/\s+/).filter(Boolean).length >= PASSAGE_WORD_COUNT;
}

/**
 * True when the Solr response looks like it didn't really answer the query —
 * no docs at all, or none of the top WEAK_SCAN_LIMIT docs share a meaningful
 * word with the query. Each doc is judged by what the modal would render for
 * it: title, subtitle, the promoted edition's title (a language-matched query
 * like "kammer" hits the German edition, not the work's English title), and
 * authors.
 *
 * Overlap is a word-boundary prefix in either direction — "gats" matches
 * "Gatsby" mid-typing, and "hobbits" matches "The Hobbit" — but both sides
 * must be meaningful words (3+ letters, no stopwords), so "art" doesn't match
 * "Bartleby" and a misspelling like "hobit" still finds no overlap and
 * correctly reads as weak.
 *
 * Queries with no meaningful words (all short/stopwords) can't be judged and
 * are treated as answered.
 *
 * @param {Array<{title?: string, subtitle?: string, author_name?: string[],
 *   editions?: {docs?: Array<{title?: string}>}}>} docs
 * @param {string} query
 * @returns {boolean}
 */
export function solrLooksWeak(docs, query) {
    if (!Array.isArray(docs) || docs.length === 0) return true;
    const meaningful = w => w.length >= 3 && !OVERLAP_STOPWORDS.has(w);
    const tokens = fold(query).split(/\W+/).filter(meaningful);
    if (tokens.length === 0) return false;
    return !docs.slice(0, WEAK_SCAN_LIMIT).some(doc => {
        if (!doc) return false;
        const edition = doc.editions && doc.editions.docs && doc.editions.docs[0];
        const haystack = [doc.title, doc.subtitle, edition && edition.title, ...(doc.author_name || [])]
            .filter(Boolean).join(' ');
        const words = fold(haystack).split(/\W+/).filter(meaningful);
        return tokens.some(t => words.some(w => w.startsWith(t) || t.startsWith(w)));
    });
}

/**
 * Split an IA fulltext snippet into segments. The API wraps each query match
 * in {{{ }}} markers; returning segments (rather than an HTML string) lets the
 * caller render matched text in a real <mark> element without ever putting
 * API-controlled text through innerHTML.
 *
 * @param {string} snippet - raw snippet text with {{{match}}} markers
 * @returns {Array<{text: string, match: boolean}>} ordered segments; empty
 *   for a missing/empty snippet
 */
export function parseSnippet(snippet) {
    if (typeof snippet !== 'string' || snippet === '') return [];
    const segments = [];
    const chunks = snippet.split('{{{');
    if (chunks[0]) segments.push({ text: chunks[0], match: false });
    for (const chunk of chunks.slice(1)) {
        const end = chunk.indexOf('}}}');
        if (end === -1) {
            // Unbalanced marker (truncated snippet) — keep the text as a
            // match rather than dropping it.
            if (chunk) segments.push({ text: chunk, match: true });
        } else {
            const matched = chunk.slice(0, end);
            const rest = chunk.slice(end + 3);
            if (matched) segments.push({ text: matched, match: true });
            if (rest) segments.push({ text: rest, match: false });
        }
    }
    return segments;
}

/**
 * Normalize one fulltext API hit into the fields the band renders. Prefers
 * the hydrated OL edition (attached server-side when a matching OL record
 * exists for the scan) and falls back to the scan's own metadata fields, so
 * a hit without an OL edition still renders instead of being dropped. (With
 * a language filter active such hits are already dropped server-side.)
 *
 * @param {Object} hit - one entry of the /search/inside.json hits.hits array
 * @returns {{ia: string, title: string, author: string, snippet: string,
 *   coverUrl: (string|null)}|null} null when the hit has no scan identifier
 *   or no snippet to show
 */
export function fulltextHitDisplay(hit) {
    const fields = (hit && hit.fields) || {};
    const ia = Array.isArray(fields.identifier) ? fields.identifier[0] : fields.identifier;
    const snippet = hit && hit.highlight && hit.highlight.text && hit.highlight.text[0];
    if (!ia || !snippet) return null;
    const edition = hit.edition || null;
    const metaTitle = Array.isArray(fields.meta_title) ? fields.meta_title[0] : fields.meta_title;
    const title = (edition && edition.title) || metaTitle || '';
    const author = (edition && Array.isArray(edition.authors)
        ? edition.authors.map((a) => a && a.name).filter(Boolean).join(', ')
        : '');
    const coverUrl = (edition && edition.cover_url) || null;
    return { ia, title, author, snippet, coverUrl };
}
