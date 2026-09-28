/**
 * Author suggestions ("B-zero") for the header search modal.
 *
 * No extra request: when the query names the author of one of the top works
 * /search.json already returned, we surface a row linking straight to that
 * author's page. This covers the common "type a name → I want that author" case
 * (the old Author facet) without a second Solr round-trip.
 *
 * Matching the query against each top result's author is self-protecting: a
 * title search ("dune") returns that author's works, but the title isn't part
 * of their name, so nothing is surfaced. Only queries that actually name an
 * author produce a row.
 *
 * Pure functions only (no lit/DOM) so they're unit-testable on their own.
 */

/** Only the top few results are relevant enough to surface their author. */
export const AUTHOR_SCAN_LIMIT = 5;

/** At most this many author rows, so an ambiguous one-word query ("smith") can't flood the list. */
export const AUTHOR_SUGGESTION_MAX = 3;

/** Lowercase and strip diacritics so "garcia" matches "García". */
function fold(s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/**
 * True when the query names the author. Matches on word boundaries only, so a
 * query can't match mid-word ("art" must not surface "Bart …"):
 *  - the full name starts with the query ("leo tol" → "Leo Tolstoy"),
 *  - the query contains the full name as whole words ("books by leo tolstoy"),
 *  - or a query word is a prefix of a name word, 3+ chars to skip
 *    initials/particles like "de" ("asimov"/"asim" → "Isaac Asimov").
 *
 * @param {string} query
 * @param {string} name
 * @returns {boolean}
 */
export function queryMatchesName(query, name) {
    const q    = fold(query).trim();
    const full = fold(name).trim();
    if (!q || !full) return false;
    if (full.startsWith(q)) return true;
    if (` ${q} `.includes(` ${full} `)) return true;
    const nameTokens = full.split(/\s+/).filter(Boolean);
    return q.split(/\s+/).some(
        token => token.length >= 3 && nameTokens.some(nt => nt.startsWith(token)),
    );
}

/**
 * Given the work docs from /search.json and the query, return the authors to
 * suggest — those of the top results whose name the query matches, in rank
 * order, deduped by key and capped. Empty when the query names none of them.
 *
 * @param {Array<{author_key?: string[], author_name?: string[]}>} docs
 * @param {string} query
 * @returns {Array<{key: string, name: string}>}
 */
export function deriveAuthors(docs, query) {
    if (!Array.isArray(docs) || docs.length === 0) return [];

    const seen = new Set();
    const authors = [];
    for (const doc of docs.slice(0, AUTHOR_SCAN_LIMIT)) {
        const key  = doc.author_key?.[0];
        const name = doc.author_name?.[0];
        if (!key || !name || seen.has(key)) continue;
        if (queryMatchesName(query, name)) {
            seen.add(key);
            authors.push({ key, name });
            if (authors.length >= AUTHOR_SUGGESTION_MAX) break;
        }
    }
    return authors;
}
