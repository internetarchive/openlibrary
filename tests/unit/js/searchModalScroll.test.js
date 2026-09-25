/**
 * A new catalog answer scrolls the results pane back to its first row. The
 * rows swap inside one long-lived .results div, so without an explicit reset
 * the previous answer's scroll offset would carry over. Exercised on a bare
 * SearchModal instance with a stand-in render root, as the other suites do.
 */
import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';

function scrolledModal({ inside = false } = {}) {
    const modal = new SearchModal();
    modal._query = 'white whale';
    modal._languages = [];
    if (inside) modal._mode = 'inside';
    const results = document.createElement('div');
    results.className = 'results';
    Object.defineProperty(results, 'scrollTop', { value: 240, writable: true });
    const root = document.createElement('div');
    root.append(results);
    Object.defineProperty(modal, 'renderRoot', { value: root });
    Object.defineProperty(modal, 'updateComplete', { value: Promise.resolve(true) });
    return { modal, results };
}

describe('scrolling back to the top', () => {
    test('a catalog answer resets the pane once it has rendered', async() => {
        const { modal, results } = scrolledModal();
        modal._scrollResultsToTop();
        expect(results.scrollTop).toBe(240);
        await modal.updateComplete;
        expect(results.scrollTop).toBe(0);
    });

    test('the Inside tab keeps its place', async() => {
        const { modal, results } = scrolledModal({ inside: true });
        modal._scrollResultsToTop();
        await modal.updateComplete;
        expect(results.scrollTop).toBe(240);
    });
});
