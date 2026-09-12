/** Pure helpers for the search modal's Search Inside band, kept DOM-free for unit tests. */

/** Word count at which an unquoted query reads as a passage, not a title. */
export const PASSAGE_WORD_COUNT = 5;

/** Top Solr docs checked by solrLooksWeak. */
export const WEAK_SCAN_LIMIT = 3;

// Too common to count as title/author overlap. Interrogatives are included so
// "how do birds navigate?" isn't "answered" by a "How to..." title.
const OVERLAP_STOPWORDS = new Set([
    'the', 'and', 'for', 'with', 'from', 'was', 'are', 'not', 'but',
    'his', 'her', 'its', 'this', 'that', 'you', 'all',
    'who', 'what', 'when', 'where', 'why', 'how',
]);

/**
 * Mirror of phrase_query in core/fulltext.py: one straight-quoted phrase so
 * BookReader finds the passage, not each word. Stray/curly quotes break FTS.
 *
 * @param {string} query
 * @returns {string} '' when nothing is left
 */
export function phraseQuery(query) {
    const words = (query || '').replace(/[\u201c\u201d\u201e\u201f]/g, '"').replace(/"/g, ' ').split(/\s+/).filter(Boolean);
    return words.length ? `"${words.join(' ')}"` : '';
}

/** Lowercase and strip diacritics so "garcia" matches "García". */
function fold(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/**
 * True for a quoted phrase or PASSAGE_WORD_COUNT+ words. A "?" isn't a signal:
 * short questions are usually titles ("Where's Waldo?").
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
 * True when none of the top docs share a meaningful word with the query. Words
 * match by prefix either way ("gats"→"Gatsby", "hobbits"→"Hobbit") but must be
 * 3+ letters, so "art" misses "Bartleby" and a typo like "hobit" reads as weak.
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
 * Split an IA snippet on its {{{match}}} markers, so matches render in <mark>
 * without API text ever going through innerHTML.
 *
 * @param {string} snippet
 * @returns {Array<{text: string, match: boolean}>}
 */
export function parseSnippet(snippet) {
    if (typeof snippet !== 'string' || snippet === '') return [];
    const segments = [];
    const chunks = snippet.split('{{{');
    if (chunks[0]) segments.push({ text: chunks[0], match: false });
    for (const chunk of chunks.slice(1)) {
        const end = chunk.indexOf('}}}');
        if (end === -1) {
            // Unbalanced marker (truncated snippet): keep the text.
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
 * Normalize a fulltext hit for the band, falling back from the hydrated OL
 * edition to the scan's own metadata so hits without an OL record still render.
 * Year always comes from meta_year; hydrated editions carry none.
 *
 * @param {Object} hit - one /search/inside.json hits.hits entry
 * @returns {{ia: string, title: string, author: string, year: string,
 *   snippet: string, coverUrl: string, coverSrcset: string}|null} null without an identifier or snippet
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
        : creatorsFromMeta(fields.meta_creator));
    const metaYear = Array.isArray(fields.meta_year) ? fields.meta_year[0] : fields.meta_year;
    const year = metaYear ? String(metaYear) : '';
    // IA cover size map matches get_ia_cover: S = 116×58, M = 180×360.
    const coverUrl = (edition && edition.cover_url) || `https://archive.org/download/${ia}/page/cover_w116_h58.jpg`;
    const coverSrcset = (edition && edition.cover_url) ? '' : `https://archive.org/download/${ia}/page/cover_w180_h360.jpg 2x`;
    return { ia, title, author, year, snippet, coverUrl, coverSrcset };
}

/** Trailing MARC relator term on some IA creator names (", author", ", ed."). */
const CREATOR_ROLE_SUFFIX = /(?:,\s*(?:joint\s+)?(?:author|editor|illustrator|translator|compiler|contributor|photographer|narrator|ed|comp|tr|ill)\.?)+$/i;

/**
 * Up to three author names from a scan's `meta_creator`. A comma with no space
 * separates packed names ("A Ganci,B Crespo"); "Last, First" stays whole.
 *
 * @param {string[]|string|undefined} metaCreator
 * @returns {string}
 */
export function creatorsFromMeta(metaCreator) {
    const values = Array.isArray(metaCreator) ? metaCreator : (metaCreator ? [metaCreator] : []);
    return values
        .flatMap((v) => String(v).split(/,(?=\S)/))
        .map((name) => name.trim().replace(CREATOR_ROLE_SUFFIX, ''))
        .filter(Boolean)
        .slice(0, 3)
        .join(', ');
}

/**
 * Drop hits whose scan is already a catalog row in the modal, by work or
 * promoted-edition `ia` (mirrors `exclude_ocaids` in core/fulltext.py).
 *
 * @param {{ia: string}[]} hits
 * @param {Object[]} docs - /search.json work docs
 * @returns {{ia: string}[]}
 */
export function dedupeFulltextHits(hits, docs) {
    const listed = new Set();
    for (const doc of docs || []) {
        for (const ocaid of doc?.ia || []) listed.add(ocaid);
        for (const ed of doc?.editions?.docs || []) {
            for (const ocaid of ed?.ia || []) listed.add(ocaid);
        }
    }
    return (hits || []).filter((hit) => !listed.has(hit.ia));
}
