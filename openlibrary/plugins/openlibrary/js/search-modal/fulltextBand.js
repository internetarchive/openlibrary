/**
 * State and fetching for the search modal's "Search inside books" band.
 *
 * Search Inside is a rescue-and-passages surface, not an every-query one, and
 * the 2020 rollback of always-on fulltext was a load story — so the decision of
 * *whether* to call the backend lives here rather than scattered across the
 * modal's input handlers. The modal tells this controller what happened
 * (`queryChanged`, `solrSettled`, `solrFailed`) and gets `{hits, total,
 * searchKey}` back through `onChange`; it never decides for itself when to
 * fetch. The published hits are an overfetched pool: the modal dedupes them
 * against its catalog rows and trims to FULLTEXT_LIMIT at render time.
 *
 * The gating heuristics themselves (isPassageQuery, solrLooksWeak) are pure
 * functions in ./fulltext.js.
 */

import { debounce } from '../nonjquery_utils.js';
import { fulltextHitDisplay, isPassageQuery, solrLooksWeak } from './fulltext.js';

/** Snippet rows in the band. Small on purpose: every fulltext hit costs
 *  availability + edition hydration server-side, and the band is a teaser
 *  pointing at /search/inside, not a result list. */
export const FULLTEXT_LIMIT = 3;

/** Hits fetched beyond FULLTEXT_LIMIT. Two consumers need the headroom: the
 *  server drops unreadable hits when the readable filter is on, and the modal
 *  drops hits that duplicate a catalog row (dedupeFulltextHits) — either way
 *  the band would thin out to a row or two without spares. */
const OVERFETCH = 3;

/** Passage-shaped queries fetch on their own timer — slower than the metadata
 *  debounce, because this is a secondary surface on an external backend. */
const PASSAGE_DEBOUNCE_MS = 800;

/**
 * Build the /search/inside query string for a query + the modal's filters.
 * Shared by the fetch and the band's "see more" link so they can't drift.
 *
 * @param {string} query
 * @param {{readable: boolean, languages: string[]}} filters
 * @returns {URLSearchParams}
 */
export function fulltextSearchParams(query, filters) {
    const params = new URLSearchParams({ q: query });
    // Any non-default availability maps to readable=true — the FTS index's
    // collections can't split open vs borrowable more finely.
    if (filters.readable) params.set('readable', 'true');
    // MARC codes; the server maps them onto languageSorter. Only the first
    // survives: the FTS backend's `lang` param takes one language and the
    // handler drops the rest, so sending more would leave the band — and the
    // "see all" URL — claiming a filter that was never applied.
    if (filters.languages.length) params.append('language', filters.languages[0]);
    return params;
}

export class FulltextBand {
    /**
     * @param {object} options
     * @param {() => {readable: boolean, languages: string[]}} options.getFilters
     * @param {(state: {hits: object[], total: number|null, searchKey: string|null}) => void} options.onChange
     * @param {(status: 'resolved'|'failed') => void} [options.onAttempt] - called
     *   once per fetch that wasn't superseded. Lets the modal count how often the
     *   band was *asked* for, not just how often it had something to show — the
     *   two differ, and only the pair gives the band's own hit rate.
     */
    constructor({ getFilters, onChange, onAttempt }) {
        this._getFilters = getFilters;
        this._onChange = onChange;
        this._onAttempt = onAttempt || (() => {});
        this._fetchKey = null;
        this.hits = [];
        this.total = null;
        // The /search/inside params these hits were measured for — the modal's
        // proof that a total still describes what its "see all" link points at.
        this.searchKey = null;
        // The passage test runs at fire time, on the query the timer settled
        // on — a timer scheduled under an older query can't fetch for the
        // edited one.
        this._debouncedPassageFetch = debounce((query) => {
            if (isPassageQuery(query)) this._fetch(query);
        }, PASSAGE_DEBOUNCE_MS, false);
    }

    /**
     * The query changed. A passage-shaped query fetches on the debounce; every
     * other query waits for Solr and comes back through solrSettled, so a clean
     * title lookup issues no fulltext request at all.
     *
     * Any in-flight response is invalidated first: without that, a band fetched
     * for the previous query can land during the debounce window and paint
     * under the edited one.
     */
    queryChanged(query) {
        this._fetchKey = null;
        this._debouncedPassageFetch(query);
    }

    /** Solr answered. A weak answer promotes the band to a rescue; a strong one
     *  clears it, so a good title match isn't trailed by a stale band. Passage
     *  queries are already fetching on their own timer — leave them alone. */
    solrSettled(query, docs) {
        if (isPassageQuery(query)) return;
        if (solrLooksWeak(docs, query)) {
            this._fetch(query);
        } else {
            this.clear();
        }
    }

    /** Solr itself failed — the fulltext band is the only rescue left, and it
     *  runs on a separate backend. */
    solrFailed(query) {
        this._fetch(query);
    }

    /** Empty the band and invalidate any in-flight fetch. */
    clear() {
        this._fetchKey = null;
        this._set([], null, null);
    }

    /** Publish new band state, skipping the notify when nothing actually
     *  changed — clear() runs on most keystrokes and would otherwise churn a
     *  re-render per stroke. */
    _set(hits, total, searchKey) {
        if (this.hits.length === 0 && hits.length === 0 && this.total === total) return;
        this.hits = hits;
        this.total = total;
        this.searchKey = searchKey;
        this._onChange({ hits, total, searchKey });
    }

    _fetch(query) {
        const trimmed = (query || '').trim();
        if (!trimmed) return;

        const filters = this._getFilters();
        const params = fulltextSearchParams(trimmed, filters);
        // Captured before the fetch-only params go on: this is the /search/inside
        // query string the results about to land describe.
        const searchKey = params.toString();
        params.set('facets', 'false');
        params.set('limit', String(FULLTEXT_LIMIT * OVERFETCH));

        const url = `/search/inside.json?${params.toString()}`;
        this._fetchKey = url;

        fetch(url)
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Fulltext search failed: ${r.status}`)))
            .then(data => {
                if (this._fetchKey !== url) return;
                const hits = data?.hits?.hits || [];
                this._set(
                    hits.map(fulltextHitDisplay).filter(Boolean),
                    typeof data?.hits?.total === 'number' ? data.hits.total : null,
                    searchKey,
                );
                this._onAttempt('resolved');
            })
            // Silent: the band simply doesn't render. It's a secondary
            // discovery surface, not the primary result list.
            .catch(() => {
                if (this._fetchKey !== url) return;
                this.clear();
                this._onAttempt('failed');
            });
    }
}
