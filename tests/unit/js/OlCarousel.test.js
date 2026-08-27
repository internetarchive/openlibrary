/**
 * Unit tests for <ol-carousel>. Motion is the browser's, so what is left to
 * test is the arithmetic around it: snap points, page offsets, scroll → page
 * mapping, and page-change timing. jsdom has no layout, so the harness stubs
 * the geometry reads. Real scrolling belongs in the Playwright suite.
 */
import { OlCarousel } from '../../../openlibrary/components/lit/OlCarousel.js';

const HOST_WIDTH = 1280;   // → 8 columns, per the component's breakpoints
const ITEM_WIDTH = 150;
const GAP = 8;
const COLUMNS = 8;

let resizeObservers;
let intersectionObservers;

beforeAll(() => {
    global.ResizeObserver = class {
        constructor(callback) {
            this.callback = callback;
            this.elements = [];
            resizeObservers.push(this);
        }
        observe(el) { this.elements.push(el); }
        disconnect() { this.elements = []; }
        /** Fire the callback as a real resize would. */
        trigger(width) {
            this.callback([{ contentRect: { width } }]);
        }
    };

    global.IntersectionObserver = class {
        constructor(callback) {
            this.callback = callback;
            this.elements = [];
            intersectionObservers.push(this);
        }
        observe(el) { this.elements.push(el); }
        unobserve(el) { this.elements = this.elements.filter((e) => e !== el); }
        disconnect() { this.elements = []; }
        /** Report `visible` as the in-view set, as a real observer batch would. */
        trigger(visible) {
            this.callback(this.elements.map((target) => ({
                target,
                isIntersecting: visible.includes(target),
            })), this);
        }
    };
});

beforeEach(() => {
    resizeObservers = [];
    intersectionObservers = [];
});

afterEach(() => {
    document.body.innerHTML = '';
    jest.useRealTimers();
});

/** Total track width for `count` items at the harness's item size. */
function trackWidth(count) {
    return count * ITEM_WIDTH + Math.max(0, count - 1) * GAP;
}

/** Mount a carousel with `count` children, stub its geometry reads, measure. */
async function mountCarousel(count, { showIndicators = false } = {}) {
    const el = document.createElement('ol-carousel');
    el.gap = GAP;
    if (showIndicators) el.showIndicators = true;

    for (let i = 0; i < count; i++) {
        const item = document.createElement('div');
        item.textContent = `Item ${i}`;
        el.appendChild(item);
    }

    Object.defineProperty(el, 'clientWidth', { value: HOST_WIDTH, configurable: true });
    document.body.appendChild(el);
    await el.updateComplete;

    const scroller = el.shadowRoot.querySelector('.viewport');
    let scrollLeft = 0;

    Object.defineProperty(scroller, 'clientWidth', { value: HOST_WIDTH, configurable: true });
    Object.defineProperty(scroller, 'scrollWidth', { value: trackWidth(count), configurable: true });
    Object.defineProperty(scroller, 'scrollLeft', {
        get: () => scrollLeft,
        set: (v) => { scrollLeft = v; },
        configurable: true,
    });
    scroller.getBoundingClientRect = () => ({ left: 0, right: HOST_WIDTH, width: HOST_WIDTH });

    // Fixed pitch, shifting with the scroll as a real scroller would.
    Array.from(el.children).forEach((item, i) => {
        item.getBoundingClientRect = () => ({
            left: i * (ITEM_WIDTH + GAP) - scrollLeft,
            width: ITEM_WIDTH,
        });
    });

    // Stand in for the browser's scroll implementation.
    scroller.scrollTo = ({ left }) => {
        scrollLeft = left;
        scroller.dispatchEvent(new Event('scroll'));
    };

    // One resize cycle drives the component's real measure path.
    resizeObservers.forEach((ro) => ro.trigger(HOST_WIDTH));
    await el.updateComplete;

    return {
        el,
        scroller,
        maxScroll: trackWidth(count) - HOST_WIDTH,
        /** Simulate the user scrolling to `left`. */
        async scrollTo(left) {
            scrollLeft = left;
            scroller.dispatchEvent(new Event('scroll'));
            await el.updateComplete;
        },
        /** Simulate the scroller coming to rest. */
        async settle() {
            scroller.dispatchEvent(new Event('scrollend'));
            await el.updateComplete;
        },
        /** Append `n` more stubbed items, as a load-more consumer would. */
        async appendItems(n) {
            const start = el.children.length;
            for (let i = 0; i < n; i++) {
                const item = document.createElement('div');
                item.textContent = `Item ${start + i}`;
                const idx = start + i;
                item.getBoundingClientRect = () => ({
                    left: idx * (ITEM_WIDTH + GAP) - scrollLeft,
                    width: ITEM_WIDTH,
                });
                el.appendChild(item);
            }
            Object.defineProperty(scroller, 'scrollWidth', {
                value: trackWidth(el.children.length),
                configurable: true,
            });
            // slotchange → recount → reactive update; flush both cycles.
            await el.updateComplete;
            await el.updateComplete;
        },
    };
}

describe('ol-carousel structure', () => {
    it('renders a labelled carousel region', async() => {
        const { el } = await mountCarousel(18);
        const region = el.shadowRoot.querySelector('.carousel');
        expect(region.getAttribute('role')).toBe('region');
        expect(region.getAttribute('aria-roledescription')).toBe('carousel');
        expect(region.getAttribute('aria-label')).toBe('Carousel');
    });

    it('makes the viewport a scroll container, not a transformed track', async() => {
        const { el, scroller } = await mountCarousel(18);
        expect(scroller).not.toBeNull();
        expect(el.shadowRoot.querySelector('.track')).toBeNull();
    });

    it('keeps arrows and edge fades outside the scroller so they do not scroll away', async() => {
        const { el, scroller } = await mountCarousel(18);
        expect(scroller.querySelector('.arrow')).toBeNull();
        expect(scroller.querySelector('.edge-fade')).toBeNull();
        expect(el.shadowRoot.querySelectorAll('.frame .arrow')).toHaveLength(2);
    });
});

describe('page arithmetic', () => {
    it('derives total pages from item count and columns', async() => {
        const { el } = await mountCarousel(18);
        expect(el.totalPages).toBe(Math.ceil(18 / COLUMNS));
    });

    it('reports a single page when everything fits', async() => {
        const { el } = await mountCarousel(5);
        expect(el.totalPages).toBe(1);
    });

    it('rests page 0 flush against the start edge', async() => {
        const { el } = await mountCarousel(18);
        expect(el._pageOffsets[0]).toBe(0);
    });

    it('offsets interior pages by the peek', async() => {
        const { el } = await mountCarousel(18);
        const peekPx = el.peek * HOST_WIDTH;
        expect(el._pageOffsets[1]).toBeCloseTo(COLUMNS * (ITEM_WIDTH + GAP) - peekPx, 5);
    });

    it('rests the ragged last page at the end of the scroll range', async() => {
        const { el, maxScroll } = await mountCarousel(18);
        expect(el._pageOffsets[el.totalPages - 1]).toBe(maxScroll);
    });

    it('maps a scroll position to the nearest page', async() => {
        const { el, scrollTo } = await mountCarousel(18);
        await scrollTo(el._pageOffsets[1] + 4);
        expect(el.page).toBe(1);
    });

    it('does not report the last page early on a ragged rail', async() => {
        // Regression guard: an evenly-spaced fraction of maxScroll would round
        // page 1 up to the final page, which sits closer than a full page away.
        const { el, scrollTo } = await mountCarousel(18);
        await scrollTo(el._pageOffsets[1]);
        expect(el.page).toBe(1);
    });
});

describe('snap points', () => {
    it('marks every column-th item as a page boundary', async() => {
        const { el } = await mountCarousel(18);
        const items = Array.from(el.children);
        expect(items[0].style.scrollSnapAlign).toBe('start');
        expect(items[COLUMNS].style.scrollSnapAlign).toBe('start');
        expect(items[1].style.scrollSnapAlign).toBe('');
    });

    it('end-aligns the final item so a short last page rests flush', async() => {
        const { el } = await mountCarousel(18);
        const items = Array.from(el.children);
        expect(items[items.length - 1].style.scrollSnapAlign).toBe('end');
    });

    it('re-applies snap points when the column count changes', async() => {
        const { el } = await mountCarousel(18);
        resizeObservers.forEach((ro) => ro.trigger(500));   // → 4 columns
        await el.updateComplete;
        const items = Array.from(el.children);
        expect(items[4].style.scrollSnapAlign).toBe('start');
        expect(items[COLUMNS].style.scrollSnapAlign).toBe('start');
        expect(items[5].style.scrollSnapAlign).toBe('');
    });
});

describe('navigation', () => {
    it('scrolls to the measured offset for a page', async() => {
        const { el, scroller } = await mountCarousel(18);
        el.goToPage(1);
        expect(scroller.scrollLeft).toBeCloseTo(el._pageOffsets[1], 5);
    });

    it('advances and retreats one page at a time', async() => {
        const { el, scroller } = await mountCarousel(18);
        el.next();
        expect(scroller.scrollLeft).toBeCloseTo(el._pageOffsets[1], 5);
        el.prev();
        expect(scroller.scrollLeft).toBe(0);
    });

    it('clamps out-of-range page requests', async() => {
        const { el, scroller, maxScroll } = await mountCarousel(18);
        el.goToPage(99);
        expect(scroller.scrollLeft).toBe(maxScroll);
        el.goToPage(-5);
        expect(scroller.scrollLeft).toBe(0);
    });

    it('updates the reported page immediately, before the scroll settles', async() => {
        const { el } = await mountCarousel(18);
        el.goToPage(2);
        expect(el.page).toBe(2);
    });

    it('leaves scroll behavior to CSS rather than forcing it in JS', async() => {
        // Omitting `behavior` is what lets the reduced-motion query apply.
        const { el, scroller } = await mountCarousel(18);
        const spy = jest.fn();
        scroller.scrollTo = spy;
        el.goToPage(1);
        expect(spy).toHaveBeenCalledWith(expect.not.objectContaining({ behavior: expect.anything() }));
    });
});

describe('page-change event', () => {
    it('fires once the scroller settles, not during the scroll', async() => {
        const { el, scrollTo, settle } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-page-change', handler);

        await scrollTo(el._pageOffsets[1]);
        expect(handler).not.toHaveBeenCalled();

        await settle();
        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler.mock.calls[0][0].detail).toEqual({ page: 1, totalPages: 3 });
    });

    it('reports only the final page after a multi-page fling', async() => {
        const { el, scrollTo, settle, maxScroll } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-page-change', handler);

        await scrollTo(el._pageOffsets[1]);
        await scrollTo(maxScroll);
        await settle();

        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler.mock.calls[0][0].detail.page).toBe(2);
    });

    it('stays quiet when the scroll settles back on the same page', async() => {
        const { el, scrollTo, settle } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-page-change', handler);

        await scrollTo(4);
        await settle();
        expect(handler).not.toHaveBeenCalled();
    });
});

describe('page-change event without native scrollend', () => {
    // Safari only shipped `scrollend` in 26.2, so this path carries iOS 18.x.
    let supported;

    beforeEach(() => {
        supported = OlCarousel._supportsScrollEnd;
        OlCarousel._supportsScrollEnd = false;
        jest.useFakeTimers();
    });

    afterEach(() => {
        OlCarousel._supportsScrollEnd = supported;
    });

    it('falls back to a debounced scroll timer', async() => {
        const { el, scrollTo } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-page-change', handler);

        await scrollTo(el._pageOffsets[1]);
        expect(handler).not.toHaveBeenCalled();

        jest.advanceTimersByTime(OlCarousel._scrollEndFallbackDelay + 10);
        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler.mock.calls[0][0].detail.page).toBe(1);
    });

    it('keeps deferring while the scroll is still moving', async() => {
        const { el, scrollTo, maxScroll } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-page-change', handler);

        await scrollTo(el._pageOffsets[1]);
        jest.advanceTimersByTime(OlCarousel._scrollEndFallbackDelay - 20);
        await scrollTo(maxScroll);
        jest.advanceTimersByTime(OlCarousel._scrollEndFallbackDelay - 20);
        expect(handler).not.toHaveBeenCalled();

        jest.advanceTimersByTime(40);
        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler.mock.calls[0][0].detail.page).toBe(2);
    });
});

describe('near-end event', () => {
    it('fires on settle within two pages of the end, not before', async() => {
        const { el, scrollTo, settle } = await mountCarousel(18);   // 3 pages
        const handler = jest.fn();
        el.addEventListener('ol-carousel-near-end', handler);

        await settle();                                             // page 0
        expect(handler).not.toHaveBeenCalled();

        await scrollTo(el._pageOffsets[1]);
        await settle();
        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler.mock.calls[0][0].detail).toEqual({ page: 1, totalPages: 3, itemCount: 18 });
    });

    it('does not fire twice for the same item count', async() => {
        const { el, scrollTo, settle, maxScroll } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-near-end', handler);

        await scrollTo(el._pageOffsets[1]);
        await settle();
        await scrollTo(maxScroll);
        await settle();
        expect(handler).toHaveBeenCalledTimes(1);
    });

    it('re-arms once items are appended', async() => {
        const { el, scrollTo, settle, appendItems } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-near-end', handler);

        await scrollTo(el._pageOffsets[1]);
        await settle();
        expect(handler).toHaveBeenCalledTimes(1);

        await appendItems(8);                                       // 26 items, 4 pages
        expect(handler).toHaveBeenCalledTimes(1);                   // buffer refilled, quiet

        await scrollTo(el._pageOffsets[2]);
        await settle();
        expect(handler).toHaveBeenCalledTimes(2);
        expect(handler.mock.calls[1][0].detail.itemCount).toBe(26);
    });

    it('fires again immediately when an append leaves the rail still near its end', async() => {
        const { el, scrollTo, settle, maxScroll, appendItems } = await mountCarousel(18);
        const handler = jest.fn();
        el.addEventListener('ol-carousel-near-end', handler);

        await scrollTo(maxScroll);
        await settle();
        expect(handler).toHaveBeenCalledTimes(1);

        await appendItems(4);                                       // 22 items — still on page 1 of 3
        expect(handler).toHaveBeenCalledTimes(2);
        expect(handler.mock.calls[1][0].detail.itemCount).toBe(22);
    });

    it('fires on first render when the rail is too short to fill the buffer', async() => {
        const handler = jest.fn();
        document.addEventListener('ol-carousel-near-end', handler);
        await mountCarousel(12);                                    // 2 pages
        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler.mock.calls[0][0].detail.itemCount).toBe(12);
        document.removeEventListener('ol-carousel-near-end', handler);
    });
});

describe('in-view tracking', () => {
    it('marks intersecting items with data-in-view and reports their indices', async() => {
        const { el } = await mountCarousel(18);
        const io = intersectionObservers[intersectionObservers.length - 1];
        io.trigger([el.children[0], el.children[1]]);
        expect(el.children[0].hasAttribute('data-in-view')).toBe(true);
        expect(el.children[2].hasAttribute('data-in-view')).toBe(false);
        expect(el.itemsInView()).toEqual([0, 1]);
    });

    it('clears the mark when an item leaves the viewport', async() => {
        const { el } = await mountCarousel(18);
        const io = intersectionObservers[intersectionObservers.length - 1];
        io.trigger([el.children[0]]);
        io.trigger([el.children[8]]);
        expect(el.children[0].hasAttribute('data-in-view')).toBe(false);
        expect(el.itemsInView()).toEqual([8]);
    });

    it('observes items appended later', async() => {
        const { el, appendItems } = await mountCarousel(18);
        await appendItems(2);
        const io = intersectionObservers[intersectionObservers.length - 1];
        expect(io.elements).toHaveLength(20);
        expect(io.elements).toContain(el.children[19]);
    });
});

describe('appending items', () => {
    it('keeps the page, offsets and scroll position when items are appended', async() => {
        const { el, scroller, scrollTo, settle, appendItems } = await mountCarousel(18);
        await scrollTo(el._pageOffsets[1]);
        await settle();
        const offsetBefore = el._pageOffsets[1];
        const scrollBefore = scroller.scrollLeft;

        await appendItems(8);

        expect(el.totalPages).toBe(4);
        expect(el.page).toBe(1);
        expect(scroller.scrollLeft).toBe(scrollBefore);
        expect(el._pageOffsets[1]).toBeCloseTo(offsetBefore, 5);
    });

    it('moves the end alignment to the new last item', async() => {
        const { el, appendItems } = await mountCarousel(18);
        await appendItems(8);
        const items = Array.from(el.children);
        expect(items[16].style.scrollSnapAlign).toBe('start');
        expect(items[17].style.scrollSnapAlign).toBe('');
        expect(items[25].style.scrollSnapAlign).toBe('end');
    });
});

describe('arrows and edge fades', () => {
    it('hides the previous arrow at the start of the rail', async() => {
        const { el } = await mountCarousel(18);
        expect(el.shadowRoot.querySelector('.arrow.prev').hidden).toBe(true);
        expect(el.shadowRoot.querySelector('.arrow.next').hidden).toBe(false);
    });

    it('hides the next arrow at the end of the rail', async() => {
        const { el, scrollTo, maxScroll } = await mountCarousel(18);
        await scrollTo(maxScroll);
        expect(el.shadowRoot.querySelector('.arrow.next').hidden).toBe(true);
        expect(el.shadowRoot.querySelector('.arrow.prev').hidden).toBe(false);
    });

    it('shows both arrows mid-rail', async() => {
        const { el, scrollTo } = await mountCarousel(18);
        await scrollTo(el._pageOffsets[1]);
        expect(el.shadowRoot.querySelector('.arrow.prev').hidden).toBe(false);
        expect(el.shadowRoot.querySelector('.arrow.next').hidden).toBe(false);
    });

    it('hides both arrows when there is only one page', async() => {
        const { el } = await mountCarousel(5);
        expect(el.shadowRoot.querySelector('.arrow.prev').hidden).toBe(true);
        expect(el.shadowRoot.querySelector('.arrow.next').hidden).toBe(true);
    });
});

describe('indicators', () => {
    it('renders one indicator per page when enabled', async() => {
        const { el } = await mountCarousel(18, { showIndicators: true });
        expect(el.shadowRoot.querySelectorAll('.indicator')).toHaveLength(3);
    });

    it('stays hidden by default', async() => {
        const { el } = await mountCarousel(18);
        expect(el.shadowRoot.querySelector('.indicators')).toBeNull();
    });

    it('keeps a single tab stop via roving tabindex', async() => {
        const { el } = await mountCarousel(18, { showIndicators: true });
        const tabbable = Array.from(el.shadowRoot.querySelectorAll('.indicator'))
            .filter((i) => i.getAttribute('tabindex') === '0');
        expect(tabbable).toHaveLength(1);
        expect(tabbable[0].getAttribute('aria-current')).toBe('true');
    });

    it('moves pages with arrow keys', async() => {
        const { el, scroller } = await mountCarousel(18, { showIndicators: true });
        const tablist = el.shadowRoot.querySelector('.indicators');
        tablist.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        await el.updateComplete;
        expect(scroller.scrollLeft).toBeCloseTo(el._pageOffsets[1], 5);
    });

    it('jumps to the ends with Home and End', async() => {
        const { el, scroller, maxScroll } = await mountCarousel(18, { showIndicators: true });
        const tablist = el.shadowRoot.querySelector('.indicators');
        tablist.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }));
        await el.updateComplete;
        expect(scroller.scrollLeft).toBe(maxScroll);

        tablist.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
        await el.updateComplete;
        expect(scroller.scrollLeft).toBe(0);
    });

    it('ignores unrelated keys', async() => {
        const { el, scroller } = await mountCarousel(18, { showIndicators: true });
        const tablist = el.shadowRoot.querySelector('.indicators');
        tablist.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
        await el.updateComplete;
        expect(scroller.scrollLeft).toBe(0);
    });
});

describe('translatable labels', () => {
    it('labels the tablist and each indicator from the English defaults', async() => {
        const { el } = await mountCarousel(18, { showIndicators: true });
        expect(el.shadowRoot.querySelector('.indicators').getAttribute('aria-label'))
            .toBe('Carousel pages');
        expect(el.shadowRoot.querySelectorAll('.indicator')[1].getAttribute('aria-label'))
            .toBe('Go to page 2 of 3');
    });

    it('takes translated labels from attributes', async() => {
        const { el } = await mountCarousel(18, { showIndicators: true });
        el.setAttribute('label-pages', 'Pages du carrousel');
        el.setAttribute('label-go-to-page', 'Aller à la page {page} sur {total}');
        await el.updateComplete;

        expect(el.shadowRoot.querySelector('.indicators').getAttribute('aria-label'))
            .toBe('Pages du carrousel');
        expect(el.shadowRoot.querySelectorAll('.indicator')[2].getAttribute('aria-label'))
            .toBe('Aller à la page 3 sur 3');
    });

    it('lets a translation reorder or drop placeholders', async() => {
        const { el } = await mountCarousel(18, { showIndicators: true });
        el.labelGoToPage = '{total} ページ中 {page} ページ目へ';
        await el.updateComplete;
        expect(el.shadowRoot.querySelectorAll('.indicator')[0].getAttribute('aria-label'))
            .toBe('3 ページ中 1 ページ目へ');

        el.labelGoToPage = 'Page {page}';
        await el.updateComplete;
        expect(el.shadowRoot.querySelectorAll('.indicator')[0].getAttribute('aria-label'))
            .toBe('Page 1');
    });

    it('leaves an unknown placeholder empty rather than printing it', async() => {
        const { el } = await mountCarousel(18, { showIndicators: true });
        el.labelGoToPage = 'Page {page} of {pages}';
        await el.updateComplete;
        expect(el.shadowRoot.querySelectorAll('.indicator')[0].getAttribute('aria-label'))
            .toBe('Page 1 of ');
    });
});

describe('covers', () => {
    it('never touches slotted images — deferring them is the browser\'s job', async() => {
        const { el } = await mountCarousel(18);
        const img = document.createElement('img');
        img.setAttribute('src', '/cover-3.jpg');
        img.setAttribute('loading', 'lazy');
        el.children[3].appendChild(img);
        await el.updateComplete;

        expect(img.getAttribute('src')).toBe('/cover-3.jpg');
        expect(img.getAttribute('loading')).toBe('lazy');
    });
});

describe('teardown', () => {
    it('disconnects the resize observer when removed', async() => {
        const { el } = await mountCarousel(18);
        el.remove();
        expect(resizeObservers[0].elements).toHaveLength(0);
    });

    it('disconnects the item observer when removed', async() => {
        const { el } = await mountCarousel(18);
        const io = intersectionObservers[intersectionObservers.length - 1];
        el.remove();
        expect(io.elements).toHaveLength(0);
    });
});
