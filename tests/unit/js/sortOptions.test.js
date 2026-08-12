import { initSortOptions } from '../../../openlibrary/plugins/openlibrary/js/sort_options.js';

// Must be `mock`-prefixed: jest hoists the factory above the declarations.
const mockTrackEvent = jest.fn();
jest.mock('../../../openlibrary/plugins/openlibrary/js/ol.analytics.js', () => ({
    trackEvent: (...args) => mockTrackEvent(...args),
}));

const ITEMS = [
    { value: 'relevance', label: 'Relevance', url: '/search?q=dune', track: 'Relevance' },
    { value: 'old', label: 'First Published', url: '/search?q=dune&sort=old', track: 'Old' },
    { value: 'want_to_read', label: 'Want to Read', nested: true, url: '/search?q=dune&sort=want_to_read', track: 'ReadingLogSubSort' },
];

// Stand-in for <ol-menu-popover>: the consumer only touches `items`, the
// `value` attribute, and the select event.
function makePopover(value = 'relevance') {
    const el = document.createElement('div');
    el.setAttribute('value', value);
    el.items = ITEMS;
    document.body.appendChild(el);
    return el;
}

function fire(el, type, value) {
    el.dispatchEvent(new CustomEvent(type, { detail: { value } }));
}

describe('initSortOptions', () => {
    let navigate;

    beforeEach(() => {
        document.body.innerHTML = '';
        mockTrackEvent.mockClear();
        // jsdom's window.location can't be replaced or spied on.
        navigate = jest.fn();
    });

    test('navigates to the committed option url', () => {
        const el = makePopover();
        initSortOptions(el, navigate);

        fire(el, 'ol-menu-popover-select', 'old');

        expect(navigate).toHaveBeenCalledWith('/search?q=dune&sort=old');
    });

    test('reports the choice to analytics under the option track key', () => {
        const el = makePopover();
        initSortOptions(el, navigate);

        fire(el, 'ol-menu-popover-select', 'want_to_read');

        expect(mockTrackEvent).toHaveBeenCalledWith('SearchSort', 'ReadingLogSubSort');
    });

    // Activating sets `value`, so the guard compares against what was rendered.
    test('does not navigate when picking the sort the page already shows', () => {
        const el = makePopover('relevance');
        initSortOptions(el, navigate);

        el.setAttribute('value', 'old');
        fire(el, 'ol-menu-popover-select', 'relevance');

        expect(navigate).not.toHaveBeenCalled();
    });

    test('ignores a selected value with no matching item', () => {
        const el = makePopover();
        initSortOptions(el, navigate);

        fire(el, 'ol-menu-popover-select', 'nonesuch');

        expect(navigate).not.toHaveBeenCalled();
    });
});
