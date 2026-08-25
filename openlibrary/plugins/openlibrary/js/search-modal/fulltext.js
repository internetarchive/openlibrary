/**
 * Helpers for the search modal's "Found inside books" band — parsing the
 * IA fulltext API's snippet markup and hit fields into renderable data.
 * Kept free of Lit/DOM so they're unit-testable.
 */

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
 * a hit without an OL edition still renders instead of being dropped.
 *
 * @param {Object} hit - one entry of the /search/inside.json hits.hits array
 * @returns {{ia: string, title: string, author: string, snippet: string,
 *   page: (number|string|null), coverUrl: (string|null)}|null} null when the
 *   hit has no scan identifier or no snippet to show
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
    // page_num arrives as a list of per-highlight lists (e.g. [[234]]);
    // flatten and take the first as the passage's page.
    const page = Array.isArray(fields.page_num)
        ? [fields.page_num].flat(Infinity)[0] ?? null
        : null;
    const coverUrl = (edition && edition.cover_url) || null;
    return { ia, title, author, snippet, page, coverUrl };
}
