/**
 * Binds the availability toggles on listing pages that own their filtering
 * locally — author pages, the reading log — where the control just rewrites one
 * query param of the current URL.
 *
 * Deliberately not SearchFilterBar: that module keeps /search's filters in
 * sessionStorage so they follow the patron across pages. These filters are
 * scoped to the page they're set on, so nothing is stored and nothing is read
 * back — the URL is the only state.
 */

import { trackEvent } from './ol.analytics.js';

/**
 * @param {Iterable<HTMLElement>} toggles - `ol-toggle` elements carrying
 *   `data-filter-param` (the query param to write) and `data-filter-value`
 *   (its value when on). Turning a toggle off drops the param entirely.
 */
export function initResultsFilterToggles(toggles) {
    for (const toggle of toggles) {
        const { filterParam, filterValue } = toggle.dataset;
        if (!filterParam || !filterValue) continue;

        toggle.addEventListener('ol-toggle-change', (e) => {
            const params = new URLSearchParams(window.location.search);
            if (e.detail.checked) {
                params.set(filterParam, filterValue);
            } else {
                params.delete(filterParam);
            }
            // The result set changes, so the current offset means nothing.
            params.delete('page');

            trackEvent('ResultsFilter', e.detail.checked ? 'AvailabilityOn' : 'AvailabilityOff');
            const query = params.toString();
            window.location.assign(query ? `${window.location.pathname}?${query}` : window.location.pathname);
        });
    }
}
