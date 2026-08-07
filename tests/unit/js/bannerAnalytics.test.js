import { initBannerAnalytics } from '../../../openlibrary/plugins/openlibrary/js/banner-analytics.js';

// Must be `mock`-prefixed: jest hoists the factory above the declarations.
const mockTrackEvent = jest.fn();
jest.mock('../../../openlibrary/plugins/openlibrary/js/ol.analytics.js', () => ({
    trackEvent: (...args) => mockTrackEvent(...args),
}));

function makeBanner({ id, dismissId } = {}) {
    const el = document.createElement('ol-banner');
    if (id) el.id = id;
    if (dismissId) el.setAttribute('dismiss-id', dismissId);
    document.body.appendChild(el);
    return el;
}

// Mirrors OlBanner.dismiss(): bubbles and composed, with dismissId in detail.
function dismiss(el, detail = {}) {
    el.dispatchEvent(new CustomEvent('ol-banner-dismiss', {
        detail,
        bubbles: true,
        composed: true,
    }));
}

describe('initBannerAnalytics', () => {
    // Registered once: the listener lives on `document`, so re-initialising per
    // test would stack listeners and multiply the call counts asserted below.
    beforeAll(() => {
        initBannerAnalytics();
    });

    beforeEach(() => {
        document.body.innerHTML = '';
        mockTrackEvent.mockClear();
    });

    it('reports a Preserve Intent banner dismissal to Matomo', () => {
        // The real banner (account/view.html) carries only an `id` — no
        // `dismiss-id` — so this is the production shape, not a synthetic one.
        dismiss(makeBanner({ id: 'pending-action-container' }));

        expect(mockTrackEvent).toHaveBeenCalledTimes(1);
        expect(mockTrackEvent).toHaveBeenCalledWith('PreserveIntent', 'Dismiss');
    });

    it('reports an unavailable-book banner dismissal to Matomo', () => {
        dismiss(makeBanner({ id: 'book-unavailable-banner' }));

        expect(mockTrackEvent).toHaveBeenCalledTimes(1);
        expect(mockTrackEvent).toHaveBeenCalledWith('OpenRelatedBooks', 'Dismiss');
    });

    it('prefers the dismissId from the event detail over the element id', () => {
        const el = makeBanner({ id: 'book-unavailable-banner' });

        dismiss(el, { dismissId: 'pending-action-container' });

        expect(mockTrackEvent).toHaveBeenCalledWith('PreserveIntent', 'Dismiss');
    });

    it('resolves a banner identified only by its dismiss-id attribute', () => {
        const el = makeBanner({ dismissId: 'pending-action-container' });

        dismiss(el);

        expect(mockTrackEvent).toHaveBeenCalledWith('PreserveIntent', 'Dismiss');
    });

    it('ignores a banner with no tracked event', () => {
        dismiss(makeBanner({ id: 'yrg26' }));

        expect(mockTrackEvent).not.toHaveBeenCalled();
    });

    it('ignores a banner with no identifier at all', () => {
        expect(() => dismiss(makeBanner())).not.toThrow();
        expect(mockTrackEvent).not.toHaveBeenCalled();
    });
});
