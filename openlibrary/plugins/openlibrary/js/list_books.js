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
        const url = new URL(window.location.href);
        url.searchParams.set('layout', layout);
        window.history.replaceState(null, '', url);
        // Shadow root, so data-ol-link-track can't see it. Same keys as before,
        // but this reports to Matomo rather than Athena.
        trackEvent('SearchLayout', layout === 'grid' ? 'Grid' : 'Details');
    }

    static init() {
        // Assume only one list-books/layout per page. The author-suggestion row
        // is deliberately not a `.list-books` (it's not books), so this only
        // ever matches the work results list.
        const listBooks = document.querySelector('.list-books');
        // Some surfaces render the list without the switcher (empty shelf).
        const layoutControl = document.querySelector('.tools--layout');
        if (!listBooks || !layoutControl) return;
        new ListBooks(listBooks, layoutControl).attach();
    }
}
