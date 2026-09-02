import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

/**
 * <ol-carousel> behaviors that only a real browser can prove. The jsdom suite
 * (tests/unit/js/OlCarousel.test.js) stubs all geometry, so real scroll-snap,
 * smooth-scroll settling, the mouse-drag pipeline (trusted pointer events,
 * Chrome's click-after-drag synthesis), and live-region updates land here.
 * Fixtures are the demos on the design page:
 *
 *   #demo-carousel        18 items, page readout in #demo-carousel-page/-total
 *   #demo-links           15 items, every card an <a href="#carousel-link-N">
 *   #demo-load-more       18 items + near-end demo appending 9 per event,
 *                         readouts in #demo-load-more-batches/-count
 *
 * Playwright's CSS engine pierces open shadow roots, so `#demo-carousel
 * .viewport` reaches the scroll container directly.
 */

const PAGE = '/developers/design/components';

const sel = {
    demo: '#demo-carousel',
    viewport: '#demo-carousel .viewport',
    nextArrow: '#demo-carousel .arrow.next',
    prevArrow: '#demo-carousel .arrow.prev',
    announcer: '#demo-carousel .announcer',
    pageReadout: '#demo-carousel-page',
    links: '#demo-links',
    linksViewport: '#demo-links .viewport',
    loadMore: '#demo-load-more',
    batches: '#demo-load-more-batches',
    count: '#demo-load-more-count',
};

async function gotoFixture(page: Page): Promise<void> {
    await page.route('https://archive.org/**', (route) => route.abort());
    await page.goto(PAGE);
    await page.waitForFunction(() => customElements.get('ol-carousel'));
    await page.locator(sel.demo).scrollIntoViewIfNeeded();
    // Wait for the component to have measured (page arithmetic ready).
    await page.waitForFunction(() =>
        (document.querySelector('#demo-carousel') as any).totalPages > 1);
}

/** Drag a carousel's viewport with the mouse: down, `steps` quick moves of
 *  `dx` each, up. Positive dx drags leftward (scrolls forward). */
async function dragViewport(page: Page, dx: number, steps = 3, viewport = sel.viewport): Promise<void> {
    const box = (await page.locator(viewport).boundingBox())!;
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    for (let i = 1; i <= steps; i++) {
        await page.mouse.move(x - (dx * i) / steps, y, { steps: 2 });
    }
    await page.mouse.up();
}

test.describe('ol-carousel', () => {
    test.beforeEach(async ({ page }) => {
        await gotoFixture(page);
    });

    test('renders a labelled region resting at page 1', async ({ page }) => {
        const region = page.locator(`${sel.demo} .carousel`);
        await expect(region).toHaveAttribute('aria-roledescription', 'carousel');
        await expect(page.locator(sel.pageReadout)).toHaveText('1');
        // At the start edge only the next arrow is available.
        await expect(page.locator(sel.prevArrow)).toBeHidden();
        await expect(page.locator(sel.nextArrow)).toBeAttached();
    });

    test('arrow click advances one page and announces it', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.locator(sel.demo).hover();
        await page.locator(sel.nextArrow).click();

        await expect(page.locator(sel.pageReadout)).toHaveText('2');
        // The polite live region tells screen-reader users the page landed.
        await expect(page.locator(sel.announcer)).toHaveText(/Page 2 of \d+/);
        expect(errors()).toHaveLength(0);
    });

    test('mouse drag advances exactly one page and swallows the click', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.evaluate((demo) => {
            (window as any).__clicks = 0;
            document.querySelector(demo)!.addEventListener('click', () => (window as any).__clicks++);
        }, sel.demo);

        // A short, fast flick: travel stays within one page of the nearest.
        await dragViewport(page, 120);
        await expect(page.locator(sel.pageReadout)).toHaveText('2');

        // Chrome fires a click on the common ancestor after a drag; the
        // component must have swallowed it before it reached a card.
        expect(await page.evaluate(() => (window as any).__clicks)).toBe(0);

        // A plain click still goes through.
        const box = (await page.locator(sel.viewport).boundingBox())!;
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        expect(await page.evaluate(() => (window as any).__clicks)).toBe(1);
        expect(errors()).toHaveLength(0);
    });

    test('plain click targets the slotted card itself', async ({ page }) => {
        // A host-level listener can't tell: retargeted clicks still bubble
        // composed through the host. Capturing the pointer at pointerdown
        // would move click's target to the shadow viewport, cutting slotted
        // buttons and links out of the path — so listen on the card.
        await page.evaluate((demo) => {
            (window as any).__cardClicks = 0;
            const card = document.querySelector(demo)!.children[0];
            card.addEventListener('click', () => (window as any).__cardClicks++);
        }, sel.demo);

        const box = await page.evaluate((demo) => {
            const r = document.querySelector(demo)!.children[0].getBoundingClientRect();
            return { x: r.x, y: r.y, width: r.width, height: r.height };
        }, sel.demo);
        await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
        expect(await page.evaluate(() => (window as any).__cardClicks)).toBe(1);
    });

    test('a hard throw lands one page over, not several', async ({ page }) => {
        // 900px of fast travel crosses page 1's offset before release;
        // without the start-page clamp this settled on page 3.
        await dragViewport(page, 900, 6);
        await expect(page.locator(sel.pageReadout)).toHaveText('2');
    });

    test('drag settle keeps scroll snapping intact afterwards', async ({ page }) => {
        await dragViewport(page, 400);
        // Settled: both transient viewport phases gone (the browser owns
        // snapping again) and the rail resting exactly on a page offset.
        await page.waitForFunction((demo) => {
            const el = document.querySelector(demo) as any;
            const viewport = el.shadowRoot.querySelector('.viewport');
            return !viewport.classList.contains('dragging')
                && !viewport.classList.contains('settling')
                && Math.abs(viewport.scrollLeft - el._pageOffsets[el.page]) < 2;
        }, sel.demo);
        // A 400px throw travels somewhere real: past page 0.
        expect(await page.evaluate((demo) =>
            (document.querySelector(demo) as any).page, sel.demo)).toBeGreaterThan(0);
    });

    test('keyboard focus into an off-page card aligns its page', async ({ page }) => {
        // Every card in this demo is a link, so Tab walks straight off the
        // first page and the rail has to follow.
        const carousel = page.locator(sel.links);
        await carousel.scrollIntoViewIfNeeded();
        await page.waitForFunction((demo) =>
            (document.querySelector(demo) as any).totalPages > 1, sel.links);

        const columns = await page.evaluate((demo) =>
            (document.querySelector(demo) as any)._columns, sel.links);

        await carousel.locator('a').first().focus();
        // One tab past the last card of page 1 lands on page 2.
        for (let i = 0; i < columns; i++) {
            await page.keyboard.press('Tab');
        }
        await expect(carousel.locator('a').nth(columns)).toBeFocused();
        await page.waitForFunction((demo) =>
            (document.querySelector(demo) as any).page === 1, sel.links);
    });

    test('a plain click on a card link navigates, a drag does not', async ({ page }) => {
        const carousel = page.locator(sel.links);
        await carousel.scrollIntoViewIfNeeded();
        await page.waitForFunction((demo) =>
            (document.querySelector(demo) as any).totalPages > 1, sel.links);

        // Clicking a card follows its href.
        await carousel.locator('a').first().click();
        await expect(page).toHaveURL(/#carousel-link-1$/);

        // Throwing the rail by the same card must not navigate: the release
        // click is swallowed, so the fragment stays where the click left it.
        await dragViewport(page, 300, 4, sel.linksViewport);
        await expect(page).toHaveURL(/#carousel-link-1$/);
        expect(await page.evaluate((demo) =>
            (document.querySelector(demo) as any).page, sel.links)).toBeGreaterThan(0);
    });

    test('near-end events drive the load-more demo until exhausted', async ({ page }) => {
        await page.locator(sel.loadMore).scrollIntoViewIfNeeded();

        for (const batch of ['1', '2', '3']) {
            await page.evaluate((loadMore) => {
                const el = document.querySelector(loadMore) as any;
                el.goToPage(el.totalPages - 1);
            }, sel.loadMore);
            await expect(page.locator(sel.batches)).toHaveText(batch);
        }
        await expect(page.locator(sel.count)).toHaveText('45');

        // The demo consumer is exhausted: another settle appends nothing.
        await page.evaluate((loadMore) => {
            const el = document.querySelector(loadMore) as any;
            el.goToPage(0);
        }, sel.loadMore);
        await page.waitForFunction((loadMore) =>
            (document.querySelector(loadMore) as any).page === 0, sel.loadMore);
        await page.evaluate((loadMore) => {
            const el = document.querySelector(loadMore) as any;
            el.goToPage(el.totalPages - 1);
        }, sel.loadMore);
        await page.waitForFunction((loadMore) => {
            const el = document.querySelector(loadMore) as any;
            return el.page === el.totalPages - 1;
        }, sel.loadMore);
        await expect(page.locator(sel.count)).toHaveText('45');
        await expect(page.locator(sel.batches)).toHaveText('3');
    });
});
