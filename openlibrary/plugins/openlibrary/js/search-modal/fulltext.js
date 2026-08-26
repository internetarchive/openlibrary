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
const OVERLAP_STOPWORDS = new Set([
    'the', 'and', 'for', 'with', 'from', 'was', 'are', 'not', 'but',
    'his', 'her', 'its', 'this', 'that', 'you', 'all',
]);

/** Lowercase and strip diacritics so "garcia" matches "García". */
function fold(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/**
 * True when the query reads like a passage rather than a title/author lookup —
 * the queries where fulltext search shines and metadata search shrugs:
 *  - a quoted phrase (straight or curly quotes): someone hunting a quotation,
 *  - a trailing question mark,
 *  - or PASSAGE_WORD_COUNT+ words (titles are usually shorter).
 *
 * @param {string} query
 * @returns {boolean}
 */
export function isPassageQuery(query) {
    const q = (query || '').trim();
    if (!q) return false;
    if (/"[^"]+"|“[^”]+”/.test(q)) return true;
    if (q.endsWith('?')) return true;
    return q.split(/\s+/).filter(Boolean).length >= PASSAGE_WORD_COUNT;
}

/**
 * True when the Solr response looks like it didn't really answer the query —
 * no docs at all, or none of the top WEAK_SCAN_LIMIT docs' title/author share
 * a meaningful word with the query. Matches on word-boundary prefixes (so
 * "gatsby" matches "Gatsby", but "art" doesn't match "Bartleby"), meaning a
 * misspelling like "hobit" finds no overlap and correctly reads as weak.
 *
 * Queries with no meaningful words (all short/stopwords) can't be judged and
 * are treated as answered.
 *
 * @param {Array<{title?: string, author_name?: string[]}>} docs
 * @param {string} query
 * @returns {boolean}
 */
export function solrLooksWeak(docs, query) {
    if (!Array.isArray(docs) || docs.length === 0) return true;
    const tokens = fold(query).split(/\W+/)
        .filter(t => t.length >= 3 && !OVERLAP_STOPWORDS.has(t));
    if (tokens.length === 0) return false;
    return !docs.slice(0, WEAK_SCAN_LIMIT).some(doc => {
        const haystack = [doc && doc.title, ...((doc && doc.author_name) || [])]
            .filter(Boolean).join(' ');
        const words = fold(haystack).split(/\W+/).filter(Boolean);
        return tokens.some(t => words.some(w => w.startsWith(t)));
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
