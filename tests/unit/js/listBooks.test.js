import { ListBooks } from '../../../openlibrary/plugins/openlibrary/js/list_books.js';

// Must be `mock`-prefixed: jest hoists the factory above the declarations.
const mockTrackEvent = jest.fn();
jest.mock('../../../openlibrary/plugins/openlibrary/js/ol.analytics.js', () => ({
    trackEvent: (...args) => mockTrackEvent(...args),
}));

// Stand-in for <ol-segmented-control>: the consumer only listens for the
// change event and reads `detail.value`.
function makeFixture() {
    const listBooks = document.createElement('ul');
    listBooks.className = 'list-books';
    const layoutControl = document.createElement('div');
    layoutControl.className = 'tools--layout';
    document.body.append(listBooks, layoutControl);
    new ListBooks(listBooks, layoutControl).attach();
    return { listBooks, layoutControl };
}

function fire(el, value) {
    el.dispatchEvent(new CustomEvent('ol-segmented-control-change', { detail: { value } }));
}

describe('ListBooks', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        document.cookie = 'LBL=; path=/; max-age=0';
        mockTrackEvent.mockClear();
        // Give each test a realistic URL with params worth preserving.
        window.history.replaceState(null, '', '/search?q=dune&sort=old');
    });

    test('toggles the grid class with the chosen layout', () => {
        const { listBooks, layoutControl } = makeFixture();

        fire(layoutControl, 'grid');
        expect(listBooks.classList.contains('list-books--grid')).toBe(true);

        fire(layoutControl, 'details');
        expect(listBooks.classList.contains('list-books--grid')).toBe(false);
    });

    test('writes the layout into the URL, preserving existing params', () => {
        const { layoutControl } = makeFixture();

        fire(layoutControl, 'grid');

        const params = new URLSearchParams(window.location.search);
        expect(params.get('layout')).toBe('grid');
        expect(params.get('q')).toBe('dune');
        expect(params.get('sort')).toBe('old');
    });

    test('updates an existing layout param instead of duplicating it', () => {
        window.history.replaceState(null, '', '/search?q=dune&layout=grid');
        const { layoutControl } = makeFixture();

        fire(layoutControl, 'details');

        expect(window.location.search).toBe('?q=dune&layout=details');
    });

    test('replaces history rather than pushing entries', () => {
        const { layoutControl } = makeFixture();
        const before = window.history.length;

        fire(layoutControl, 'grid');
        fire(layoutControl, 'details');

        expect(window.history.length).toBe(before);
    });

    test('persists the layout in the LBL cookie', () => {
        const { layoutControl } = makeFixture();

        fire(layoutControl, 'grid');

        expect(document.cookie).toContain('LBL=grid');
    });

    test('reports the layout change to analytics', () => {
        const { layoutControl } = makeFixture();

        fire(layoutControl, 'grid');

        expect(mockTrackEvent).toHaveBeenCalledWith('SearchLayout', 'Grid');
    });
});
