import { trackEvent } from './ol.analytics.js';

/**
 * Navigates the sort <ol-menu-popover> (search/sort_options.html). Items carry
 * the changequery URL the server built, so paging and the rest of the query
 * are handled there.
 *
 * @param {HTMLElement} menu The <ol-menu-popover> element
 * @param {function(string): void} [navigate] Test seam — jsdom's
 *   window.location can be neither replaced nor spied on.
 */
export function initSortOptions(menu, navigate = (url) => window.location.assign(url)) {
    // Read up front: activating an item updates `value`, so it stops
    // describing what the page is showing.
    const renderedValue = menu.getAttribute('value');

    menu.addEventListener('ol-menu-popover-select', function(event) {
        const value = event.detail.value;
        // Re-picking the sort the page is already showing: nothing to load.
        if (value === renderedValue) return;
        const item = (menu.items || []).find(i => i.value === value);
        if (!item) return;
        // Shadow root, so data-ol-link-track can't see it — report by hand.
        trackEvent('SearchSort', item.track);
        navigate(item.url);
    });
}
