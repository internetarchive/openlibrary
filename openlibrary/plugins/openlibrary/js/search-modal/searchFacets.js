/**
 * Service module — context-aware facet counts.
 *
 * Sole owner of the /search/facets.json URL and response shape.
 * Mirrors the fetchLanguageOptions() pattern in search-modal/languages.js.
 */

const FACETS_URL = '/search/facets.json';

/**
 * Fetch context-aware facet value counts for a single Solr field.
 *
 * @param {string} field - A field name from WorkSearchScheme.facet_fields,
 *     e.g. 'language', 'author_facet', 'subject_facet'.
 * @param {URLSearchParams} searchParams - The current page search params
 *     (q, availability flags, etc.) forwarded as-is to the backend.
 * @returns {Promise<Array<{value: string, count: number}>>}
 *     Count-descending list of {value, count} pairs (count > 0 only).
 */
export async function fetchFacetCounts(field, searchParams) {
    const params = new URLSearchParams(searchParams);
    params.set('field', field);

    const response = await fetch(`${FACETS_URL}?${params.toString()}`);
    if (!response.ok) {
        throw new Error(`fetchFacetCounts: HTTP ${response.status} for field="${field}"`);
    }

    const data = await response.json();

    // The API returns either shape for forward-compatibility with multi-field
    //   Flat array (single-field):  [{value, count}, ...]
    //   Field-keyed map (multi):    { "language": [{value, count}], ... }
    if (Array.isArray(data)) return data;
    return data[field] ?? [];
}
