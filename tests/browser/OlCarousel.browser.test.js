/**
 * Browser-mode tests for <ol-carousel>.
 *
 * tests/unit/js/OlCarousel.test.js runs 1,000+ lines, most of it a harness
 * faking the browser away: stubbed ResizeObserver and IntersectionObserver,
 * hand-written getBoundingClientRect, a fake scrollTo and a synthetic
 * scrollend. That is the only way to test a component whose behaviour *is*
 * geometry in jsdom, where clientWidth is 0 and nothing can scroll.
 *
 * Here the harness is gone. The browser measures, snaps, scrolls, settles and
 * announces, and the tests assert what a reader actually gets.
 */
import { expect, test } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OlCarousel.js';

/** A rail of 18 cards, 1280px viewport minus body margins → 8 columns, 3 pages. */
async function mountCarousel() {
    render(html`
        <ol-carousel label="Trending" style="width: 1200px">
            ${Array.from({ length: 18 }, (_, i) => html`
                <div style="height: 120px">Card ${i}</div>
            `)}
        </ol-carousel>
    `);

    const el = document.querySelector('ol-carousel');
    await el.updateComplete;
    // The first ResizeObserver pass lands after connect; wait it out.
    await expect.poll(() => el.totalPages).toBe(3);

    return {
        el,
        scroller: el.shadowRoot.querySelector('.viewport'),
    };
}

test('real layout decides the columns, the pages and the snap points', async() => {
    await page.viewport(1280, 800);
    const { el, scroller } = await mountCarousel();

    // Real overflow. jsdom cannot produce this number: its scrollWidth is
    // always 0 and the unit suite had to define it by hand.
    expect(scroller.scrollWidth).toBeGreaterThan(scroller.clientWidth);

    // Real scroll-snap on real slotted cards — page boundaries every 8th
    // item, the ragged last card end-aligned, interior cards left alone.
    const items = Array.from(el.children);
    expect(items[0].style.scrollSnapAlign).toBe('start');
    expect(items[8].style.scrollSnapAlign).toBe('start');
    expect(items[1].style.scrollSnapAlign).toBe('');
    expect(items[17].style.scrollSnapAlign).toBe('end');
});

test('Next really scrolls the rail, settles it, and announces the page', async() => {
    await page.viewport(1280, 800);
    const { el, scroller } = await mountCarousel();

    // A trusted click on the shadow-DOM arrow (locators pierce open roots).
    await page.getByRole('button', { name: 'Next page' }).click();

    // The browser owns this scroll: smooth behaviour, then snap, then
    // scrollend, then the live-region announcement. Auto-retrying assertions
    // ride the whole sequence instead of guessing a sleep length.
    await expect.element(page.getByText('Page 2 of 3')).toBeInTheDocument();
    await expect.poll(() => scroller.scrollLeft, 'the rail settled on page 1')
        .toBeCloseTo(el._pageOffsets[1], 0);

    // The reported page agrees with where the rail actually is.
    expect(el.page).toBe(1);
});
