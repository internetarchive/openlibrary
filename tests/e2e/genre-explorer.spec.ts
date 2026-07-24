import { test, expect, Page } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

/**
 * Genre Explorer (/explore/genres) scroll & gesture UX.
 *
 * The whole explorer renders inside the <ol-library-explorer> web component's shadow
 * root, so state assertions reach in via shadowRoot. Shelves are built from the bundled
 * genre.json (no Solr needed), so these structural checks run even where book data is
 * absent -- only the book carousels stay empty. We deliberately DO NOT assert the feel of
 * trackpad momentum (synthetic wheel events don't reproduce it); we assert the mechanism:
 * native scroll-snap config, home/sticky/scroll-away layout, and the horizontal gate.
 */

const URL = '/explore/genres';

/** Read genre-mode scroll state from inside the component's shadow root. */
async function state(page: Page) {
    return page.evaluate(() => {
        const host = document.querySelector('ol-library-explorer');
        const root = host && host.shadowRoot;
        if (!root) return null;
        const room = root.querySelector('.book-room') as HTMLElement | null;
        if (!room) return null;
        const shelves = [...root.querySelectorAll('.shelf')] as HTMLElement[];
        const filter = root.querySelector('.genre-filter-bar') as HTMLElement | null;
        const nav = root.querySelector('.genre-top-nav-wrapper') as HTMLElement | null;
        const home = root.querySelector('.genre-scroll-home') as HTMLElement | null;
        const cs = (el: Element | null) => (el ? getComputedStyle(el) : null);
        return {
            genreMode: room.classList.contains('genre-mode'),
            roomSnapType: cs(room)!.scrollSnapType,
            roomOverflowY: cs(room)!.overflowY,
            roomScrolls: room.scrollHeight > room.clientHeight,
            roomScrollTop: Math.round(room.scrollTop),
            shelfCount: shelves.length,
            shelfAlign: shelves[0] ? cs(shelves[0])!.scrollSnapAlign : null,
            shelfStop: shelves[0] ? cs(shelves[0])!.scrollSnapStop : null,
            homeExists: !!home,
            homeStop: home ? cs(home)!.scrollSnapStop : null,
            navPosition: nav ? cs(nav)!.position : null,
            navTop: nav ? Math.round(nav.getBoundingClientRect().top) : null,
            filterTop: filter ? Math.round(filter.getBoundingClientRect().top) : null,
            filterVisible: filter ? filter.getBoundingClientRect().bottom > 0 : false,
        };
    });
}

const setRoomScroll = (page: Page, y: number) =>
    page.evaluate((top) => {
        const room = document.querySelector('ol-library-explorer')!.shadowRoot!
            .querySelector('.book-room') as HTMLElement;
        room.scrollTop = top;
    }, y);

const activeGenre = (page: Page) =>
    page.evaluate(() => {
        const a = document.querySelector('ol-library-explorer')!.shadowRoot!
            .querySelector('.genre-top-nav__item.active');
        return a ? a.textContent!.trim() : null;
    });

/** Skip gracefully if the component bundle didn't mount (e.g. unbuilt in this env). */
async function skipIfNotMounted(page: Page) {
    const mounted = await page.locator('ol-library-explorer').count();
    test.skip(mounted === 0, 'LibraryExplorer component not mounted in this environment');
    const s = await state(page);
    test.skip(!s || s.shelfCount === 0, 'Genre shelves did not render in this environment');
}

test.describe('Genre Explorer scroll UX @smoke', () => {
    test('loads in genre mode with shelves and no JS errors', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto(URL);
        await page.waitForTimeout(1500);
        await skipIfNotMounted(page);
        const s = (await state(page))!;
        expect(s.genreMode).toBe(true);
        expect(s.shelfCount).toBeGreaterThan(0);
        expect(errors()).toHaveLength(0);
    });

    test('vertical: shelves snap inside a bounded pane, one shelf per gesture', async ({ page }) => {
        await page.goto(URL);
        await page.waitForTimeout(1500);
        await skipIfNotMounted(page);
        const s = (await state(page))!;
        // The pane -- not the document -- is the scroll container.
        expect(s.roomOverflowY).toBe('auto');
        expect(s.roomScrolls).toBe(true);
        // Mandatory snap + stop:always = "snap to each shelf, one gesture one shelf".
        expect(s.roomSnapType).toContain('y');
        expect(s.roomSnapType).toContain('mandatory');
        expect(s.shelfAlign).toBe('start');
        expect(s.shelfStop).toBe('always');
    });

    test('home: loads at the top with the controls (0th shelf) visible', async ({ page }) => {
        await page.goto(URL);
        await page.waitForTimeout(1500);
        await skipIfNotMounted(page);
        const s = (await state(page))!;
        expect(s.roomScrollTop).toBe(0);
        // The non-sticky sentinel anchors "home" and is a hard stop like the shelves.
        expect(s.homeExists).toBe(true);
        expect(s.homeStop).toBe('always');
        // Filter controls are visible at home.
        expect(s.filterVisible).toBe(true);
    });

    test('scroll: nav stays sticky, filter controls scroll up and away', async ({ page }) => {
        await page.goto(URL);
        await page.waitForTimeout(1500);
        await skipIfNotMounted(page);
        const home = (await state(page))!;
        expect(home.navPosition).toBe('sticky');
        const filterTopAtHome = home.filterTop!;
        // Scroll well down inside the pane.
        await setRoomScroll(page, 1400);
        await page.waitForTimeout(300);
        const deep = (await state(page))!;
        // Nav is still pinned near the top of the pane...
        expect(deep.navTop).toBeLessThanOrEqual(home.navTop! + 2);
        // ...while the filter has scrolled up and away (further up than it was at home).
        expect(deep.filterTop!).toBeLessThan(filterTopAtHome);
    });
});

test.describe('Genre Explorer horizontal genre switch @smoke', () => {
    // The switch fires on a wheel with |deltaX| > |deltaY|, except over a book carousel,
    // and only while at or above the 1st shelf. A single synthetic wheel event is enough
    // to exercise the gate (this is not a momentum/feel assertion).
    async function swipeOverShelfLabel(page: Page, shelfIndex: number) {
        const pt = await page.evaluate((i) => {
            const shelves = document.querySelector('ol-library-explorer')!.shadowRoot!
                .querySelectorAll('.shelf');
            const shelf = shelves[i] as HTMLElement;
            const label = (shelf.querySelector('.shelf-label') || shelf) as HTMLElement;
            const r = label.getBoundingClientRect();
            return { x: Math.round(r.left + r.width / 2), y: Math.max(160, Math.round(r.top + 3)) };
        }, shelfIndex);
        await page.mouse.move(pt.x, pt.y);
        await page.mouse.wheel(140, 0);
        await page.waitForTimeout(500);
    }

    test('switches genres from home / the 1st shelf', async ({ page }) => {
        await page.goto(URL);
        await page.waitForTimeout(1500);
        await skipIfNotMounted(page);
        await setRoomScroll(page, 0);
        const before = await activeGenre(page);
        await swipeOverShelfLabel(page, 0);
        const after = await activeGenre(page);
        expect(after).not.toBe(before);
    });

    test('does NOT switch genres once scrolled past the 1st shelf', async ({ page }) => {
        await page.goto(URL);
        await page.waitForTimeout(1500);
        await skipIfNotMounted(page);
        const s = (await state(page))!;
        test.skip(s.shelfCount < 3, 'Needs at least 3 shelves to scroll onto the 2nd');
        // Snap onto the 2nd shelf, then attempt a horizontal swipe.
        await setRoomScroll(page, 470);
        await page.waitForTimeout(300);
        const before = await activeGenre(page);
        await swipeOverShelfLabel(page, 1);
        const after = await activeGenre(page);
        expect(after).toBe(before);
    });
});

test.describe('Library Explorer (DDC/LCC) is unaffected', () => {
    test('/explore does not use genre-mode scroll-snap', async ({ page }) => {
        await page.goto('/explore');
        await page.waitForTimeout(1500);
        const mounted = await page.locator('ol-library-explorer').count();
        test.skip(mounted === 0, 'LibraryExplorer component not mounted in this environment');
        const s = await page.evaluate(() => {
            const room = document.querySelector('ol-library-explorer')!.shadowRoot!
                .querySelector('.book-room') as HTMLElement;
            const cs = getComputedStyle(room);
            return { genreMode: room.classList.contains('genre-mode'), snapType: cs.scrollSnapType };
        });
        expect(s.genreMode).toBe(false);
        expect(s.snapType).toBe('none');
    });
});
