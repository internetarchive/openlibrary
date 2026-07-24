/**
 * Gesture state-machine tests for <ol-carousel>.
 *
 * The carousel's drag physics live in plain pointer handlers with no Lit
 * rendering dependency, so we mock the `lit` module (keeping the test
 * independent of a Lit transform in Jest, like focusableHostMixin.test.js)
 * and drive the handlers with synthetic event objects on a detached element.
 *
 * Geometry used throughout: clientWidth 800, 24 items, 6 columns → 4 pages.
 * Page offsets (in % of width): 0, -92, -187, -279.
 */

jest.mock('lit', () => ({
    LitElement: class extends globalThis.HTMLElement {
        connectedCallback() {}
        disconnectedCallback() {}
    },
    html: (strings, ...values) => ({ strings, values }),
    css: (strings, ...values) => ({ strings, values }),
    nothing: {},
}));

import '../../../openlibrary/components/lit/OlCarousel.js';

/** Create a detached carousel with fixed geometry and reduced-motion springs
 *  (which settle synchronously, so page-change events fire inline). */
function createCarousel() {
    window.matchMedia = jest.fn(() => ({ matches: true }));
    const el = document.createElement('ol-carousel');
    Object.defineProperty(el, 'clientWidth', { value: 800 });
    el._itemCount = 24;
    el._columns = 6;
    el._totalPages = 4;
    el._page = 0;
    el._currentPos = 0;

    const pageChanges = [];
    el.addEventListener('ol-carousel-page-change', (e) => pageChanges.push(e.detail));
    return { el, pageChanges };
}

function pointerEvent(clientX, clientY, overrides = {}) {
    return { button: 0, pointerId: 1, pointerType: 'touch', clientX, clientY, ...overrides };
}

function keyEvent(key) {
    return { key, preventDefault: jest.fn() };
}

function wheelEvent(deltaX, deltaY = 0, overrides = {}) {
    return { deltaX, deltaY, deltaMode: 0, preventDefault: jest.fn(), ...overrides };
}

afterEach(() => {
    jest.restoreAllMocks();
});

describe('OlCarousel axis lock (touch)', () => {
    test('mostly-vertical movement abandons the drag without navigating', () => {
        const { el, pageChanges } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(498, 140)); // dy 40 ≫ dx 2

        expect(el._dragging).toBe(false);
        expect(el._page).toBe(0);
        expect(pageChanges).toEqual([]);
    });

    test('movement inside the dead zone neither locks nor moves the track', () => {
        const { el } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(496, 103)); // dx 4, dy 3 — under threshold

        expect(el._axisLock).toBe(null);
        expect(el._dragging).toBe(true);
    });

    test('mostly-horizontal movement locks the gesture to the carousel', () => {
        const { el } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(488, 101)); // dx -12 ≫ dy 1

        expect(el._axisLock).toBe('x');
        expect(el._draggedPastThreshold).toBe(true);
    });

    test('angled swipes (steeper than 45° but within the bias) still catch', () => {
        const { el } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(490, 115)); // dx 10, dy 15 — ~56° from horizontal

        expect(el._axisLock).toBe('x');
    });

    test('horizontal swipe past the flick threshold advances a page', () => {
        const { el, pageChanges } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(488, 101)); // locks x, re-anchors at 488
        el._onPointerMove(pointerEvent(390, 103)); // delta -98 > 10% of 800
        el._onPointerUp(pointerEvent(390, 103));

        expect(el._page).toBe(1);
        expect(pageChanges).toEqual([{ page: 1, totalPages: 4 }]);
    });

    test('mouse pointers lock horizontal immediately (no dead-zone dance)', () => {
        const { el, pageChanges } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100, { pointerType: 'mouse' }));
        expect(el._axisLock).toBe('x');

        el._onPointerMove(pointerEvent(400, 100, { pointerType: 'mouse' }));
        el._onPointerUp(pointerEvent(400, 100, { pointerType: 'mouse' }));

        expect(el._page).toBe(1);
        expect(pageChanges).toEqual([{ page: 1, totalPages: 4 }]);
    });
});

describe('OlCarousel pointercancel', () => {
    test('browser claiming the gesture mid-drag never navigates', () => {
        const { el, pageChanges } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(488, 101)); // locks x
        el._onPointerMove(pointerEvent(300, 103)); // big drag with velocity
        el._onPointerCancel(pointerEvent(300, 103));

        expect(el._dragging).toBe(false);
        expect(el._page).toBe(0);
        expect(pageChanges).toEqual([]);
    });
});

describe('OlCarousel release physics', () => {
    test('stale velocity is discarded: drag, hold, release does not flick', () => {
        const { el, pageChanges } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(488, 101)); // locks x, re-anchors
        el._onPointerMove(pointerEvent(418, 101)); // delta -70, under 80px threshold
        // Simulate a fast drag followed by a 200ms hold before release
        el._velocity = -1.5;
        el._pointerPrevTime = performance.now() - 200;
        el._onPointerUp(pointerEvent(418, 101));

        expect(el._page).toBe(0);
        expect(pageChanges).toEqual([{ page: 0, totalPages: 4 }]);
    });

    test('fresh velocity still flicks a short drag to the next page', () => {
        const { el } = createCarousel();

        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(488, 101)); // locks x, re-anchors
        el._onPointerMove(pointerEvent(418, 101)); // delta -70, under 80px threshold
        el._velocity = -1.5; // px/ms, recent (prev time just set by the move)
        el._onPointerUp(pointerEvent(418, 101));

        expect(el._page).toBe(1);
    });

    test('a long drag lands on the nearest page, not just ±1', () => {
        const { el, pageChanges } = createCarousel();

        el._onPointerDown(pointerEvent(1800, 100));
        el._onPointerMove(pointerEvent(1788, 101)); // locks x, re-anchors at 1788
        el._onPointerMove(pointerEvent(188, 103)); // delta -1600 = -200% ≈ page 2 (-187%)
        el._pointerPrevTime = performance.now() - 200; // no momentum
        el._onPointerUp(pointerEvent(188, 103));

        expect(el._page).toBe(2);
        expect(pageChanges).toEqual([{ page: 2, totalPages: 4 }]);
    });
});

describe('OlCarousel page-scroll suppression', () => {
    test('touchmove is prevented only while locked horizontal', () => {
        const { el } = createCarousel();
        const prevented = () => {
            const e = { cancelable: true, preventDefault: jest.fn() };
            el._onTouchMove(e);
            return e.preventDefault.mock.calls.length > 0;
        };

        el._onPointerDown(pointerEvent(500, 100));
        expect(prevented()).toBe(false); // axis not resolved yet

        el._onPointerMove(pointerEvent(488, 101)); // locks x
        expect(prevented()).toBe(true); // carousel owns the gesture

        el._onPointerUp(pointerEvent(488, 101));
        expect(prevented()).toBe(false); // drag over
    });
});

describe('OlCarousel consecutive swipes', () => {
    test('a second touch swipe works after the first completes', () => {
        const { el, pageChanges } = createCarousel();

        // Swipe 1
        el._onPointerDown(pointerEvent(500, 100));
        el._onPointerMove(pointerEvent(488, 101));
        el._onPointerMove(pointerEvent(390, 103));
        el._onPointerUp(pointerEvent(390, 103));
        expect(el._page).toBe(1);

        // Swipe 2 (new pointerId, as on iOS)
        el._onPointerDown(pointerEvent(500, 100, { pointerId: 2 }));
        el._onPointerMove(pointerEvent(488, 101, { pointerId: 2 }));
        el._onPointerMove(pointerEvent(390, 103, { pointerId: 2 }));
        el._onPointerUp(pointerEvent(390, 103, { pointerId: 2 }));

        expect(el._page).toBe(2);
        expect(pageChanges.map((d) => d.page)).toEqual([1, 2]);
    });
});

describe('OlCarousel indicator keyboard navigation', () => {
    test('ArrowRight advances a page and preventDefaults', () => {
        const { el, pageChanges } = createCarousel();

        const e = keyEvent('ArrowRight');
        el._onIndicatorKeydown(e);

        expect(el._page).toBe(1);
        expect(pageChanges).toEqual([{ page: 1, totalPages: 4 }]);
        expect(e.preventDefault).toHaveBeenCalled();
    });

    test('ArrowLeft goes to the previous page', () => {
        const { el, pageChanges } = createCarousel();
        el._page = 2;
        el._currentPos = el._getOffsetForPage(2);

        el._onIndicatorKeydown(keyEvent('ArrowLeft'));

        expect(el._page).toBe(1);
        expect(pageChanges).toEqual([{ page: 1, totalPages: 4 }]);
    });

    test('Home and End jump to the first and last pages', () => {
        const { el } = createCarousel();

        el._onIndicatorKeydown(keyEvent('End'));
        expect(el._page).toBe(3);

        el._onIndicatorKeydown(keyEvent('Home'));
        expect(el._page).toBe(0);
    });

    test('ArrowLeft at the first page is a no-op (no navigation, still consumed)', () => {
        const { el, pageChanges } = createCarousel();

        const e = keyEvent('ArrowLeft');
        el._onIndicatorKeydown(e);

        expect(el._page).toBe(0);
        expect(pageChanges).toEqual([]);
        expect(e.preventDefault).toHaveBeenCalled();
    });

    test('ArrowRight at the last page is a no-op', () => {
        const { el, pageChanges } = createCarousel();
        el._page = 3;
        el._currentPos = el._getOffsetForPage(3);

        el._onIndicatorKeydown(keyEvent('ArrowRight'));

        expect(el._page).toBe(3);
        expect(pageChanges).toEqual([]);
    });

    test('unrelated keys are ignored and not consumed', () => {
        const { el } = createCarousel();

        const e = keyEvent('Enter');
        el._onIndicatorKeydown(e);

        expect(el._page).toBe(0);
        expect(e.preventDefault).not.toHaveBeenCalled();
    });
});

describe('OlCarousel horizontal wheel (trackpad swipe)', () => {
    test('a horizontal swipe past the threshold pages forward and is consumed', () => {
        const { el, pageChanges } = createCarousel();

        const e = wheelEvent(50, 2); // dx 50 ≫ dy 2, over 40px threshold
        el._onWheel(e);

        expect(el._page).toBe(1);
        expect(pageChanges).toEqual([{ page: 1, totalPages: 4 }]);
        expect(e.preventDefault).toHaveBeenCalled();
    });

    test('a leftward swipe pages backward', () => {
        const { el } = createCarousel();
        el._page = 2;
        el._currentPos = el._getOffsetForPage(2);

        el._onWheel(wheelEvent(-50));

        expect(el._page).toBe(1);
    });

    test('vertical-dominant wheel is left to the page (not consumed, no paging)', () => {
        const { el, pageChanges } = createCarousel();

        const e = wheelEvent(5, 60); // dy 60 ≫ dx 5
        el._onWheel(e);

        expect(el._page).toBe(0);
        expect(pageChanges).toEqual([]);
        expect(e.preventDefault).not.toHaveBeenCalled();
    });

    test('accumulated horizontal drift under the threshold does not page', () => {
        const { el } = createCarousel();

        el._onWheel(wheelEvent(12, 1));
        el._onWheel(wheelEvent(12, 1));
        el._onWheel(wheelEvent(12, 1)); // 36px total, still under 40

        expect(el._page).toBe(0);
    });

    test('one gesture pages once even as momentum keeps firing events', () => {
        const { el } = createCarousel();

        el._onWheel(wheelEvent(50)); // crosses threshold → page 1, locks
        el._onWheel(wheelEvent(50)); // momentum tail
        el._onWheel(wheelEvent(50)); // momentum tail

        expect(el._page).toBe(1);
    });

    test('after the gesture goes idle, a fresh swipe pages again', () => {
        jest.useFakeTimers();
        const { el } = createCarousel();

        el._onWheel(wheelEvent(50)); // → page 1, locks
        el._onWheel(wheelEvent(50)); // swallowed
        expect(el._page).toBe(1);

        jest.advanceTimersByTime(200); // outlast _wheelGestureEndDelay (150ms)

        el._onWheel(wheelEvent(50)); // new gesture → page 2
        expect(el._page).toBe(2);

        jest.useRealTimers();
    });

    test('line-mode deltas are normalised so a small line count still pages', () => {
        const { el } = createCarousel();

        el._onWheel(wheelEvent(3, 0, { deltaMode: 1 })); // 3 lines × 16 = 48px

        expect(el._page).toBe(1);
    });
});
