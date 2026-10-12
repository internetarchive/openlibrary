import { initLazyCarousel } from '../../../openlibrary/plugins/openlibrary/js/lazy-carousel.js';

// Must be `mock`-prefixed: vitest hoists the factory above the declarations.
const mockTrackEvent = vi.fn();
vi.mock('../../../openlibrary/plugins/openlibrary/js/ol.analytics.js', () => ({
    trackEvent: (...args) => mockTrackEvent(...args),
}));
vi.mock('../../../openlibrary/plugins/openlibrary/js/carousel', () => ({
    initialzeCarousels: () => {},
}));

const flushPromises = () => new Promise(resolve => setTimeout(resolve, 0));

class ImmediatelyVisibleObserver {
    constructor(callback) {
        this.callback = callback;
    }

    observe(target) {
        this.callback([{isIntersecting: true, target}], this);
    }

    unobserve() {}
    disconnect() {}
}

function makePlaceholder(config) {
    const elem = document.createElement('div');
    elem.className = 'lazy-carousel';
    elem.dataset.config = JSON.stringify(config);
    elem.innerHTML = `
        <div class="loadingIndicator"></div>
        <div class="lazy-carousel-retry hidden"><a class="retry-btn"></a></div>
        <div class="lazy-carousel-fallback hidden"></div>`;
    document.body.replaceChildren(elem);
    return elem;
}

function respondWith(partials) {
    global.fetch = vi.fn().mockResolvedValue({ok: true, json: async() => ({partials})});
}

describe('lazy carousel impressions', () => {
    const originalFetch = global.fetch;
    const originalIntersectionObserver = global.IntersectionObserver;

    beforeEach(() => {
        mockTrackEvent.mockClear();
        global.IntersectionObserver = ImmediatelyVisibleObserver;
    });

    afterEach(() => {
        global.fetch = originalFetch;
        global.IntersectionObserver = originalIntersectionObserver;
    });

    test('reports one impression for a carousel with books', async() => {
        respondWith('<div class="carousel carousel--progressively-enhanced"></div>');
        initLazyCarousel([makePlaceholder({key: 'nearby-books'})]);
        await flushPromises();

        expect(mockTrackEvent).toHaveBeenCalledTimes(1);
        expect(mockTrackEvent).toHaveBeenCalledWith('BookCarousel', 'Impression', 'nearby-books');
    });

    test('reports nothing when the partial is empty', async() => {
        respondWith('');
        initLazyCarousel([makePlaceholder({key: 'nearby-books'})]);
        await flushPromises();

        expect(mockTrackEvent).not.toHaveBeenCalled();
    });

    test('reports nothing when the fallback message is shown instead', async() => {
        respondWith('');
        initLazyCarousel([makePlaceholder({key: 'related-subjects-carousel', fallback: true})]);
        await flushPromises();

        expect(mockTrackEvent).not.toHaveBeenCalled();
    });
});

describe('lazy carousel requires_user', () => {
    const originalFetch = global.fetch;
    const originalIntersectionObserver = global.IntersectionObserver;

    beforeEach(() => {
        global.IntersectionObserver = ImmediatelyVisibleObserver;
    });

    afterEach(() => {
        global.fetch = originalFetch;
        global.IntersectionObserver = originalIntersectionObserver;
        delete document.body.dataset.userKey;
    });

    test('removes the placeholder without fetching when logged out', () => {
        respondWith('');
        const elem = makePlaceholder({partial: 'ContinueReading', requires_user: true});
        initLazyCarousel([elem]);

        expect(global.fetch).not.toHaveBeenCalled();
        expect(elem.isConnected).toBe(false);
    });

    test('fetches when logged in, without sending the flag', async() => {
        respondWith('');
        document.body.dataset.userKey = '/people/openlibrary';
        initLazyCarousel([makePlaceholder({partial: 'ContinueReading', requires_user: true})]);
        await flushPromises();

        expect(global.fetch).toHaveBeenCalledTimes(1);
        expect(String(global.fetch.mock.calls[0][0])).toContain('ContinueReading');
        expect(String(global.fetch.mock.calls[0][0])).not.toContain('requires_user');
    });
});
