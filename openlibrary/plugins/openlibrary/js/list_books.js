import { trackEvent } from './ol.analytics.js';

export class ListBooks {
    /**
     * @param {HTMLElement} listBooks
     * @param {HTMLElement} layoutControl The <ol-segmented-control> layout switcher
     **/
    constructor(listBooks, layoutControl) {
        this.listBooks = listBooks;
        this.layoutControl = layoutControl;
    }

    attach() {
        this.layoutControl.addEventListener('ol-segmented-control-change', this.updateLayout.bind(this));
    }

    /**
     * @param {CustomEvent} event
     */
    updateLayout(event) {
        const layout = event.detail.value;
        this.listBooks.classList.toggle('list-books--grid', layout === 'grid');
        document.cookie = `LBL=${layout}; path=/; max-age=31536000`;
        // The control lives in a shadow root, where the data-ol-link-track click
        // trigger can't see it, so report the switch ourselves. Category/action
        // keep the old key names, but this reports to Matomo rather than Athena
        // — the same move SearchFilterBar made for the availability toggle.
        trackEvent('SearchLayout', layout === 'grid' ? 'Grid' : 'Details');
    }

    static init() {
        // Assume only one list-books/layout per page. The author-suggestion row
        // is deliberately not a `.list-books` (it's not books), so this only
        // ever matches the work results list.
        const listBooks = document.querySelector('.list-books');
        const layoutControl = document.querySelector('.tools--layout');
        // Some surfaces render the results list without the layout switcher
        // (e.g. an empty or single-result shelf).
        if (!listBooks || !layoutControl) return;
        new ListBooks(listBooks, layoutControl).attach();
    }
}
