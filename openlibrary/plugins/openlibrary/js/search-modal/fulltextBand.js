/**
 * Decides when the search modal queries Search Inside, and holds its state.
 * It backs two surfaces: the band under the Books tab, whose fetches are gated
 * to passages and Solr rescues (always-on fulltext was rolled back in 2020 over
 * backend load), and the Inside books tab, where picking the tab *is* the
 * request — so in explicit mode every query fetches, and deeper.
 */

import { debounce } from '../nonjquery_utils.js';
import { fulltextHitDisplay, isPassageQuery, solrLooksWeak } from './fulltext.js';

/** Small because each hit costs server-side hydration; the band is a teaser. */
export const FULLTEXT_LIMIT = 3;

/** The Inside tab is the destination, not a teaser, so it asks for a full page. */
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
        // Set while the Inside books tab is showing: every query fetches, and
        // the gates below step aside.
        this.explicit = false;
        // Whether a fetch is outstanding. Only the Inside tab renders it — the
        // band stays silent until hits land.
        this.loading = false;
        // Both test the mode at fire time, so switching tabs (or an edit that
        // stops being a passage) cancels a timer the other mode started.
        this._debouncedPassageFetch = debounce((query) => {
            if (!this.explicit && isPassageQuery(query)) this._fetch(query);
        }, PASSAGE_DEBOUNCE_MS, false);
        this._debouncedExplicitFetch = debounce((query) => {
            if (this.explicit) this._fetch(query, INSIDE_LIMIT);
        }, EXPLICIT_DEBOUNCE_MS, false);
    }

    /**
     * Enter or leave the Inside tab. The previous mode's hits are dropped
     * rather than reused: they were fetched at the other depth. Switching *to*
     * the tab fetches at once — the click is the intent, so there's nothing to
     * debounce.
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
            // Ahead of the debounce, so the tab shows a spinner the moment the
            // query moves rather than 400ms of results that no longer match.
            this._setLoading(Boolean((query || '').trim()));
            this._debouncedExplicitFetch(query);
        } else {
            this._debouncedPassageFetch(query);
        }
    }

    /** A weak Solr answer fetches as a rescue; a strong one clears the band.
     *  Passage queries already fetch on their own timer. */
    solrSettled(query, docs) {
        // The tab doesn't ride on the catalog's answer, and clearing here would
        // wipe hits the patron explicitly asked for.
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
        this._set([], null, null);
    }

    _notify() {
        this._onChange({ hits: this.hits, total: this.total, searchKey: this.searchKey, loading: this.loading });
    }

    _setLoading(loading) {
        if (this.loading === loading) return;
        this.loading = loading;
        this._notify();
    }

    /** Skips no-op notifies; clear() runs on most keystrokes. */
    _set(hits, total, searchKey) {
        const unchanged = this.hits.length === 0 && hits.length === 0 && this.total === total && !this.loading;
        this.hits = hits;
        this.total = total;
        this.searchKey = searchKey;
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
