
/** @typedef {import('./classes.js').ExtractedBook} ExtractedBook */
/** @typedef {import('./classes.js').MatchOptions} MatchOptions */
/** @typedef {import('./classes.js').BookMatch} BookMatch */

const OL_SEARCH_BASE = 'openlibrary.org'

/**
 * @param {ExtractedBook} extractedBook
 * @param {MatchOptions} matchOptions
 */
export function buildSearchUrl(extractedBook, matchOptions, json = true) {
    let title = extractedBook.title?.split(/[:(?]/)[0].replace(/’/g, '\'');
    const author = extractedBook.author
    title = title.replace(/^the\b/i, '').trim();
    let query = `title:"${title}"`;
    if (matchOptions.includeAuthor && author  && author.toLowerCase() !== 'null' && author.toLowerCase() !== 'unknown') {
        const authorParts = author.replace(/^\S+\./, '').trim().split(/\s/);
        const authorLastName = author.includes(',') ? author.replace(/,.*/, '') : authorParts[authorParts.length - 1];
        query += ` author:${authorLastName}`;
    }
    let path = `https://${OL_SEARCH_BASE}/search`;
    if (json) path += '.json';
    const url = `${path}?${new URLSearchParams({
        q: query,
        mode: 'everything',
        fields: 'key,title,author_name,cover_i,first_publish_year,edition_count,ebook_access',
    })}`;
    return url;
}

