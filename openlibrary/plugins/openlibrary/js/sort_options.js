import { trackEvent } from './ol.analytics.js';

/**
 * Wires the sort <ol-menu-popover> (openlibrary/templates/search/sort_options.html)
 * to navigation. Each item carries the URL the server built for it with
 * changequery, so picking one preserves the rest of the query and resets paging
 * without this module having to know anything about search params.
 *
 * Only activation fires `ol-menu-popover-select` — arrowing through the menu
 * moves focus and nothing else — so it's safe to navigate straight from it.
 *
 * @param {HTMLElement} menu The <ol-menu-popover> element
 * @param {function(string): void} [navigate] Overrides how a chosen URL is
 *   loaded. Only for tests — jsdom's window.location can be neither replaced
 *   nor spied on, so the navigation needs an injectable seam.
 */
export function initSortOptions(menu, navigate = (url) => window.location.assign(url)) {
    // The sort this page was rendered with. Read once, up front: activating an
    // item updates `value`, so it stops describing what the page is showing.
    const renderedValue = menu.getAttribute('value');

    menu.addEventListener('ol-menu-popover-select', function(event) {
        const value = event.detail.value;
        // Re-picking the sort the page is already showing: nothing to load.
        if (value === renderedValue) return;
        const item = (menu.items || []).find(i => i.value === value);
        if (!item) return;
        // The menu lives in a shadow root, where the data-ol-link-track click
        // trigger can't see it, so report the choice ourselves.
        trackEvent('SearchSort', item.track);
        navigate(item.url);
    });
}
