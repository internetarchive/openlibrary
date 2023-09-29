const commonRegex = {
    wikidata: /^https?:\/\/www\.wikidata\.org\/wiki\/(Q[1-9]\d*)$/,
    // viaf regex from https://www.wikidata.org/wiki/Property:P214#P8966
    viaf: /^https?:\/\/(?:www\.)?viaf\.org\/viaf\/([1-9]\d(?:\d{0,7}|\d{17,20}))($|\/|\?|#)/,
    // note: storygraph seems to use the same format for works and editions
    storygraph: /^https?:\/\/app\.thestorygraph\.com\/books\/([0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12})$/,

}
const workIdentifierExtractionPatterns = {
    wikidata: commonRegex.wikidata,
    viaf: commonRegex.viaf,
    storygraph: commonRegex.storygraph,
    // librarything regex from https://www.wikidata.org/wiki/Property:P1085#P8966
    librarything: /^https?:\/\/www\.librarything\.(?:com|nl)\/work\/(\d+)/,
    // goodreads regex from https://www.wikidata.org/wiki/Property:P8383#P8966
    goodreads: /^https?:\/\/www\.goodreads\.com\/work\/editions\/(\d+)/,

}

/**
 * Compares url string against regex patters to extract work identifier.
 * @param {String} url
 * @returns {Array} [work identifier, identifier type] or null, null
 */
export function extractWorkIdFromUrl(url) {
    return extractIdFromUrl(url, workIdentifierExtractionPatterns);
}
/**
 * Compares url string against regex patters to extract identifier.
 * @param {String} url
 * @param {Object} patters - object of regex patterns
 * @returns {Array} [identifier, identifier type] or null, null
 */
function extractIdFromUrl(url, patterns) {
    for (const idtype in patterns) {
        const extractPattern = patterns[idtype];
        const id = extractPattern.exec(url);
        if (id && id[1]) {
            return [id[1], idtype];
        }
    }
    return [null, null];
}
