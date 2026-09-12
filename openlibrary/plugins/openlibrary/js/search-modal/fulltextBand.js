/**
 * Decides when the search modal's band queries Search Inside, and holds its
 * state. Fetches are gated to passages and Solr rescues: always-on fulltext
 * was rolled back in 2020 over backend load.
 */

import { debounce } from '../nonjquery_utils.js';
import { fulltextHitDisplay, isPassageQuery, solrLooksWeak } from './fulltext.js';

/** Small because each hit costs server-side hydration; the band is a teaser. */
export const FULLTEXT_LIMIT = 3;

/** Spare hits, since readable filtering and catalog dedupe both drop some. */
const OVERFETCH = 3;

/** Slower than the metadata debounce: a secondary surface on an external backend. */
const PASSAGE_DEBOUNCE_MS = 800;

/**
 * /search/inside params for a query + filters, shared by the fetch and the
 * "see all" link so they can't drift.
 *
 * @param {string} query
 * @param {{readable: boolean, languages: string[]}} filters
 * @returns {URLSearchParams}
 */
export function fulltextSearchParams(query, filters) {
    const params = new URLSearchParams({ q: query });
    // FTS can't split open vs borrowable, so any availability filter maps here.
    if (filters.readable) params.set('readable', 'true');
    // The FTS backend takes one language; sending more would misreport the filter.
    if (filters.languages.length) params.append('language', filters.languages[0]);
    return params;
}

export class FulltextBand {
    /**
     * @param {object} options
     * @param {() => {readable: boolean, languages: string[]}} options.getFilters
     * @param {(state: {hits: object[], total: number|null, searchKey: string|null}) => void} options.onChange
     * @param {(status: 'resolved'|'failed') => void} [options.onAttempt] - once per
     *   non-superseded fetch, so the modal can measure the band's hit rate.
     */
    constructor({ getFilters, onChange, onAttempt }) {
        this._getFilters = getFilters;
        this._onChange = onChange;
        this._onAttempt = onAttempt || (() => {});
        this._fetchKey = null;
        this.hits = [];
        this.total = null;
        // Params these hits were fetched for, so the modal can tell a total
        // still matches its "see all" link.
        this.searchKey = null;
        // Tested at fire time, so an edit that stops being a passage cancels the fetch.
        this._debouncedPassageFetch = debounce((query) => {
            if (isPassageQuery(query)) this._fetch(query);
        }, PASSAGE_DEBOUNCE_MS, false);
    }

    /** Passage queries fetch on the debounce; others wait for solrSettled. Also
     *  invalidates any in-flight fetch so a stale band can't paint. */
    queryChanged(query) {
        this._fetchKey = null;
        this._debouncedPassageFetch(query);
    }

    /** A weak Solr answer fetches as a rescue; a strong one clears the band.
     *  Passage queries already fetch on their own timer. */
    solrSettled(query, docs) {
        if (isPassageQuery(query)) return;
        if (solrLooksWeak(docs, query)) {
            this._fetch(query);
        } else {
            this.clear();
        }
    }

    /** Fulltext runs on a separate backend, so it can still rescue a Solr failure. */
    solrFailed(query) {
        this._fetch(query);
    }

    /** Empty the band and invalidate any in-flight fetch. */
    clear() {
        this._fetchKey = null;
        this._set([], null, null);
    }

    /** Skips no-op notifies; clear() runs on most keystrokes. */
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
        // Captured before the fetch-only params below.
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
            // Silent: the band is secondary, so it just doesn't render.
            .catch(() => {
                if (this._fetchKey !== url) return;
                this.clear();
                this._onAttempt('failed');
            });
    }
}
