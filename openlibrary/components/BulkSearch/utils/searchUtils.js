
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
    // Remove leading articles from title; these can sometimes be missing from OL records,
    // and will hence cause a failed match.
    // Taken from https://github.com/internetarchive/openlibrary/blob/4d880c1bf3e2391dd001c7818052fd639d38ff58/conf/solr/conf/managed-schema.xml#L526
    title = title.replace(/^(an? |the |l[aeo]s? |l'|de la |el |il |un[ae]? |du |de[imrst]? |das |ein |eine[mnrs]? |bir )/i, '').trim();
    const query = [];

    if (title) {
        query.push(`title:"${title}"`);
    }
    if (matchOptions.includeAuthor && author  && author.toLowerCase() !== 'null' && author.toLowerCase() !== 'unknown') {
        const authorParts = author.replace(/^\S+\./, '').trim().split(/\s/);
        const authorLastName = author.includes(',') ? author.replace(/,.*/, '') : authorParts[authorParts.length - 1];
        query.push(`author:${authorLastName}`);
    }

    if (extractedBook.isbn) {
        query.push(`isbn:${extractedBook.isbn}`);
    }

    let path = `https://${OL_SEARCH_BASE}/search`;
    if (json) path += '.json';
    const url = `${path}?${new URLSearchParams({
        q: query.join(' '),
        mode: 'everything',
        fields: 'key,title,author_name,cover_i,first_publish_year,edition_count,ebook_access',
    })}`;
    return url;
}

