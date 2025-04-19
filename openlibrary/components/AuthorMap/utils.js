/**
 * @param {string} countryCode - The ISO 3166-1 alpha-2 code of the country.
 * @param {number} limit - The maximum number of authors to return.
 */
export async function queryWikidata(countryCode, limit) {
    const endpointUrl = 'https://query.wikidata.org/sparql';
    const sparqlQuery = `
  SELECT DISTINCT ?x ?xLabel ?olid
  WHERE {
    ?x wdt:P31 wd:Q5.            # ?x is an instance of human
    ?x wdt:P648 ?olid.           # ?x has an Open Library ID
    ?x wdt:P27/wdt:P297 "${countryCode}".    # ?x has country of citizenship (P27) whose ISO 3166-1 alpha-2 code (P297) is "${countryCode}"
    SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
  }
  LIMIT ${limit}`;

    // Encode the query for use in a URL
    const fullUrl = `${endpointUrl}?query=${encodeURIComponent(sparqlQuery)}`;
    const headers = { Accept: 'application/sparql-results+json' };

    const response = await fetch(fullUrl, { headers });
    if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
    }
    const data = await response.json();
    const bindings = data.results.bindings;
    const OLIDs = bindings.map(binding => binding.olid.value);
    return OLIDs;
}

/**
 * Fetches author data from Open Library using their OLIDs.
 * @param {string[]} olids - An array of Open Library IDs.
 * @returns {Promise<Object[]>} - A promise that resolves to an array of author objects.
 */
export async function queryOLAuthors(olids) {
    const endpointUrl = 'https://openlibrary.org/search/authors.json';
    const query = olids.map(olid => `"/authors/${olid}"`).join(' OR ');
    const fullUrl = `${endpointUrl}?q=key:(${encodeURIComponent(query)})`;

    const response = await fetch(fullUrl);
    const data = await response.json();
    const docs = data.docs;
    return docs;
}

/**
 * Fetches authors for a given country code.
 * @param {string} countryCode - The ISO 3166-1 alpha-2 code of the country.
 * @param {number} limit - The maximum number of authors to return.
 */
export async function getAuthorsForCountry(countryCode = 'CA', limit = 15){
    const OLIDs = await queryWikidata(countryCode, limit);
    return await queryOLAuthors(OLIDs);
}
