/**
 * Decides when the search modal queries Search Inside. The Books tab's band is
 * gated to passages and Solr rescues; the Inside tab (explicit mode) fetches every query.
 */

import { debounce } from '../nonjquery_utils.js';
import { fulltextHitDisplay, isPassageQuery, solrLooksWeak } from './fulltext.js';

/** Small because each hit costs server-side hydration; the band is a teaser. */
export const FULLTEXT_LIMIT = 3;

/** The Inside tab is the destination, so it asks for a full page. */
export const INSIDE_LIMIT = 10;

/** Spare hits, since readable filtering and catalog dedupe both drop some. */
const OVERFETCH = 3;

/** Slower than the metadata debounce: a secondary surface on an external backend. */
const PASSAGE_DEBOUNCE_MS = 800;

/** The tab is the only thing on screen, so it answers at typeahead speed. */
const EXPLICIT_DEBOUNCE_MS = 400;

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
        // The query the hits on screen answer; BookReader links quote this, not the input.
        this.query = '';
        // Inside tab showing: every query fetches, bypassing the gates.
        this.explicit = false;
        // A fetch is outstanding. Only the Inside tab shows it.
        this.loading = false;
        // Both check the mode at fire time, so a tab switch cancels the other's timer.
        this._debouncedPassageFetch = debounce((query) => {
            if (!this.explicit && isPassageQuery(query)) this._fetch(query);
        }, PASSAGE_DEBOUNCE_MS, false);
        this._debouncedExplicitFetch = debounce((query) => {
            if (this.explicit) this._fetch(query, INSIDE_LIMIT);
        }, EXPLICIT_DEBOUNCE_MS, false);
    }

    /**
     * Enter or leave the Inside tab, dropping the other depth's hits.
     * Entering fetches at once, without the debounce.
     *
     * @param {boolean} explicit
     * @param {string} query - fetched immediately when entering; pass '' to skip
     */
    setExplicit(explicit, query = '') {
        if (this.explicit === explicit) return;
        this.explicit = explicit;
        this.clear();
        if (explicit) this._fetch(query, INSIDE_LIMIT);
    }

    /** Passage queries fetch on the debounce; others wait for solrSettled. Also
     *  invalidates any in-flight fetch so a stale band can't paint. */
    queryChanged(query) {
        this._fetchKey = null;
        if (this.explicit) {
            // Set before the debounce so the spinner shows immediately.
            this._setLoading(Boolean((query || '').trim()));
            this._debouncedExplicitFetch(query);
        } else {
            this._debouncedPassageFetch(query);
        }
    }

    /** A weak Solr answer fetches as a rescue; a strong one clears the band.
     *  Passage queries already fetch on their own timer. */
    solrSettled(query, docs) {
        // The tab doesn't depend on the catalog's answer.
        if (this.explicit) return;
        if (isPassageQuery(query)) return;
        if (solrLooksWeak(docs, query)) {
            this._fetch(query);
        } else {
            this.clear();
        }
    }

    /** Fulltext runs on a separate backend, so it can still rescue a Solr failure. */
    solrFailed(query) {
        if (this.explicit) return;
        this._fetch(query);
    }

    /** Empty the band and invalidate any in-flight fetch. */
    clear() {
        this._fetchKey = null;
        this._set([], null, null, '');
    }

    _notify() {
        this._onChange({
            hits: this.hits,
            total: this.total,
            searchKey: this.searchKey,
            query: this.query,
            loading: this.loading,
        });
    }

    _setLoading(loading) {
        if (this.loading === loading) return;
        this.loading = loading;
        this._notify();
    }

    /** Skips no-op notifies; clear() runs on most keystrokes. */
    _set(hits, total, searchKey, query) {
        const unchanged = this.hits.length === 0 && hits.length === 0 && this.total === total && !this.loading;
        this.hits = hits;
        this.total = total;
        this.searchKey = searchKey;
        this.query = query;
        this.loading = false;
        if (!unchanged) this._notify();
    }

    _fetch(query, limit = FULLTEXT_LIMIT * OVERFETCH) {
        const trimmed = (query || '').trim();
        if (!trimmed) {
            this._setLoading(false);
            return;
        }
        this._setLoading(true);

        const filters = this._getFilters();
        const params = fulltextSearchParams(trimmed, filters);
        // Captured before the fetch-only params below.
        const searchKey = params.toString();
        params.set('facets', 'false');
        params.set('limit', String(limit));

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
                    trimmed,
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
