/**
 * Service module — context-aware facet counts for the filter droppers.
 *
 * Sole owner of the /search/facets.json URL and response shape, of the merge
 * into a catalogue list, and of when a dropper is allowed to open.
 * Mirrors the fetchLanguageOptions() pattern in search-modal/languages.js.
 */

const FACETS_PATH = '/search/facets.json';

// Filter params to drop when counting a given field, where the param name isn't
// just the field name: /search accepts either spelling of the author filter.
const OWN_FILTER_PARAMS = {
    author_facet: ['author_facet', 'author_key'],
};

// How long a dropper stays shut waiting for its counts before opening anyway.
// The facet query is a single rows=0 Solr call, so it normally lands well
// inside this and the panel opens once, already counted and sorted. Past the
// budget an unexplained dead trigger is the worse failure, so we open on the
// catalogue and let the counts land in the panel.
export const FACET_OPEN_BUDGET_MS = 500;

/**
 * Fetch context-aware facet value counts for a single Solr field.
 *
 * @param {string} field - A field name from WorkSearchScheme.facet_fields,
 *     e.g. 'language', 'author_facet', 'subject_facet'.
 * @param {URLSearchParams} searchParams - The current page search params
 *     (q, availability flags, etc.) forwarded to the backend, minus any filter
 *     on `field` itself.
 * @returns {Promise<Array<{value: string, count: number}>>}
 *     Count-descending list of {value, count} pairs (count > 0 only).
 */
export async function fetchFacetCounts(field, searchParams) {
    const params = new URLSearchParams(searchParams);

    // Solr ANDs every fq, including one on the field being counted, so leaving
    // `language=eng` in would report zero for every other language and shrink
    // the dropper to what's already ticked — no way back to a second choice.
    for (const name of OWN_FILTER_PARAMS[field] ?? [field]) {
        params.delete(name);
    }
    params.set('field', field);

    const response = await fetch(`${FACETS_PATH}?${params.toString()}`);
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

/**
 * Merge context-aware facet counts into a catalogue list, then sort and filter
 * per the issue spec: count-descending, zero-count values hidden — except a
 * value the patron currently has selected, which stays visible (at 0) so it can
 * still be unticked.
 *
 * Merged on `value` (the filter token, e.g. the MARC code `eng`) rather than
 * the display label: both sides localize their labels independently, so a label
 * join would silently drop every row under some UI languages.
 *
 * @param {Array<{value: string, label: string}>} items - Full catalogue list.
 * @param {Array<{value: string, count: number}>} counts - API response.
 * @param {string[]} selectedValues - Currently selected item values.
 * @returns {Array<{value: string, label: string, count: number}>}
 */
export function mergeFacetCounts(items, counts, selectedValues) {
    const countMap = new Map(counts.map(c => [c.value, c.count]));
    const selectedSet = new Set(selectedValues);

    return items
        .map(it => ({ ...it, count: countMap.get(it.value) ?? 0 }))
        .filter(it => it.count > 0 || selectedSet.has(it.value))
        .sort((a, b) => b.count - a.count);
}

/**
 * Handle an `ol-select-popover-request-open` by loading the counts first, so
 * the panel opens once at its final size rather than swapping a spinner for a
 * shorter, re-sorted list under the pointer.
 *
 * The load is raced against FACET_OPEN_BUDGET_MS: whichever finishes first, the
 * panel opens. Losing the race is not an error — the panel just opens on the
 * uncounted catalogue and the counts merge in behind its own loading state.
 *
 * @param {CustomEvent} event - The cancelable request-open event.
 * @param {() => Promise<void>} load - Loads the counts into the popover's items.
 * @returns {Promise<void>}
 */
export async function openWhenCountsReady(event, load) {
    event.preventDefault();
    const popover = event.currentTarget;
    const { focusFirst } = event.detail;

    let timer;
    const budget = new Promise(resolve => { timer = setTimeout(resolve, FACET_OPEN_BUDGET_MS); });
    try {
        await Promise.race([load(), budget]);
    } finally {
        clearTimeout(timer);
        popover.show({ focusFirst });
    }
}
