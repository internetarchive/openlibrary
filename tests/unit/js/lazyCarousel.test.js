import { initLazyCarousel, initLoadedCarousels } from '../../../openlibrary/plugins/openlibrary/js/lazy-carousel.js';

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
        <div class="carousel-skeleton"></div>
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

describe('pre-loaded row impressions', () => {
    const originalIntersectionObserver = global.IntersectionObserver;

    beforeEach(() => {
        mockTrackEvent.mockClear();
        global.IntersectionObserver = ImmediatelyVisibleObserver;
    });

    afterEach(() => {
        global.IntersectionObserver = originalIntersectionObserver;
    });

    test('reports an impression for a row that arrives loaded', async() => {
        const shelf = document.createElement('div');
        shelf.innerHTML = `
            <div class="lazy-carousel-loaded" data-config='{"key": "genre-horror"}'>
                <div class="carousel carousel--progressively-enhanced"></div>
            </div>
            <div class="lazy-carousel-loaded" data-config='{"key": "genre-horror-empty"}'></div>`;
        document.body.replaceChildren(shelf);
        initLoadedCarousels(shelf);
        await flushPromises();

        expect(mockTrackEvent).toHaveBeenCalledTimes(1);
        expect(mockTrackEvent).toHaveBeenCalledWith('BookCarousel', 'Impression', 'genre-horror');
    });
});

describe('lazy carousel empty rows', () => {
    const originalFetch = global.fetch;
    const originalIntersectionObserver = global.IntersectionObserver;

    beforeEach(() => {
        global.IntersectionObserver = ImmediatelyVisibleObserver;
    });

    afterEach(() => {
        global.fetch = originalFetch;
        global.IntersectionObserver = originalIntersectionObserver;
    });

    test('drops a row that loads with nothing to show', async() => {
        respondWith('<div class="carousel-section"></div>');
        initLazyCarousel([makePlaceholder({key: 'genre-horror-gothic'})]);
        await flushPromises();

        expect(document.querySelector('.lazy-carousel')).toBeNull();
        expect(document.querySelector('.lazy-carousel-loaded')).toBeNull();
    });

    test('keeps a grid row, which has cards but no carousel to initialize', async() => {
        respondWith('<div class="carousel carousel--grid"></div>');
        initLazyCarousel([makePlaceholder({key: 'grid-row', layout: 'grid'})]);
        await flushPromises();

        expect(document.querySelector('.lazy-carousel')).toBeNull();
        expect(document.querySelector('.lazy-carousel-loaded .carousel--grid')).not.toBeNull();
    });
});
