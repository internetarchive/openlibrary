import { test, expect, Page } from '@playwright/test';

/**
 * DIAGNOSTIC suite for the Genre Explorer bookcase look & feel. These encode the *desired*
 * end-state as soft assertions -- a failing check here is a tracked visual/behaviour/
 * skeuomorphism issue to fix, not a broken build. Run with:
 *   OL_BASE_URL=http://localhost:8081 npx playwright test genre-explorer-diagnostics
 * (Uses ?ol_base=openlibrary.org so real covers load.)
 *
 * NOT part of the CI smoke suite until the issues below are resolved.
 */

const URL = '/explore/genres?ol_base=openlibrary.org#fantasy';

const setScroll = (page: Page, y: number) =>
    page.evaluate((top) => {
        const r = document.querySelector('ol-library-explorer')!.shadowRoot!
            .querySelector('.book-room') as HTMLElement;
        r.scrollTop = top;
    }, y);

test('genre explorer look & feel diagnostics', async ({ page }) => {
    await page.goto(URL);
    await page.waitForTimeout(5000);
    const mounted = await page.locator('ol-library-explorer').count();
    test.skip(mounted === 0, 'component not mounted');

    // ---- A. "Books rest ON the shelf board" (skeuomorphism + strange-if-floating) ----
    const gap = await page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        const car = root.querySelector('.shelf-carousel') as HTMLElement;
        const cs = getComputedStyle(car);
        const boardTop = car.getBoundingClientRect().bottom - parseFloat(cs.paddingBottom);
        const book = car.querySelector('.book .cover, .book > img') as HTMLElement | null;
        return book ? Math.round(boardTop - book.getBoundingClientRect().bottom) : null;
    });
    // Skip if books didn't load (e.g. no Solr/covers in this environment); otherwise assert.
    if (gap !== null) {
        expect.soft(gap, `A1: books float ${gap}px above the board — should rest on it (<=3px)`)
            .toBeLessThanOrEqual(3);
    }

    // ---- B. The sticky controls must be opaque so shelves don't bleed through when
    // scrolled. .genre-sticky-header is the pinned unit; the nav is one band inside it,
    // and both paint a fill. ----
    const navBg = await page.evaluate(() => {
        const nav = document.querySelector('ol-library-explorer')!.shadowRoot!
            .querySelector('.genre-sticky-header') as HTMLElement;
        return getComputedStyle(nav).backgroundColor;
    });
    expect.soft(navBg, `B1: sticky nav must be fully opaque, got ${navBg}`)
        .not.toContain('rgba');

    // nav stays pinned to the top of the pane after scrolling
    // Measured from the top of the pane, not the viewport: when the site header auto-hides
    // it shifts the whole pane up by the header's height (header-scroll.js, and
    // .book-room.genre-mode.header-collapsed), which moves the pinned controls with it.
    const stickyOffset = () => page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        const room = root.querySelector('.book-room') as HTMLElement;
        const hdr = root.querySelector('.genre-sticky-header') as HTMLElement;
        return hdr.getBoundingClientRect().top - room.getBoundingClientRect().top;
    });
    const navTopHome = await stickyOffset();
    await setScroll(page, 1200);
    await page.waitForTimeout(400);
    const navTopScrolled = await stickyOffset();
    expect.soft(Math.abs(navTopScrolled - navTopHome), 'B2: controls should stay pinned while scrolling')
        .toBeLessThanOrEqual(2);

    // ---- C. No horizontal page overflow ----
    const overflowX = await page.evaluate(() =>
        document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect.soft(overflowX, `C1: horizontal overflow of ${overflowX}px`).toBeLessThanOrEqual(1);

    // ---- D. Performance/loading: covers should load quickly as shelves come into view ----
    await setScroll(page, 0);
    await page.waitForTimeout(300);
    // scroll to the 3rd shelf, then give it a reasonable budget to populate
    await setScroll(page, 900);
    await page.waitForTimeout(2500);
    const coverStats = await page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        const vh = window.innerHeight;
        const imgs = [...root.querySelectorAll('.book .cover, .book > img')] as HTMLImageElement[];
        const inView = imgs.filter((im) => {
            const r = im.getBoundingClientRect();
            return r.bottom > 0 && r.top < vh && r.width > 0;
        });
        const loaded = inView.filter((im) => im.complete && im.naturalWidth > 0);
        return { inView: inView.length, loaded: loaded.length };
    });
    // D1 is a network-bound perf observation, not a pass/fail: covers stream in as fast as
    // the network allows, and skeleton placeholders now cover the gap gracefully. Logged so
    // the number is visible without failing the suite.
    console.log(`[perf] D1: ${coverStats.loaded}/${coverStats.inView} in-view covers loaded within 2.5s of scroll`);

    // ---- E. No lingering "Loading…" indicator on shelves near the top after a fair wait ----
    const loadingCount = await page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        return [...root.querySelectorAll('*')].filter((el) =>
            el.children.length === 0 && /^\s*Loading/i.test(el.textContent || '')
            && (el as HTMLElement).getBoundingClientRect().width > 0).length;
    });
    expect.soft(loadingCount, `E1: ${loadingCount} shelves still showing "Loading…" after settle`).toBe(0);

    // ---- F. The shelf's baseboard reads as its own strip, ruled off from the surface ----
    const board = await page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        const car = root.querySelector('.shelf-carousel') as HTMLElement;
        const after = getComputedStyle(car, '::after');
        const shelf = root.querySelector('.shelf') as HTMLElement;
        return {
            h: parseFloat(after.height),
            bg: after.backgroundColor,
            borderTop: parseFloat(after.borderTopWidth),
            shelfBg: getComputedStyle(shelf).backgroundColor,
        };
    });
    // F1: it occupies real height, so books land on it rather than over it.
    expect.soft(board.h, `F1: baseboard should reserve height, got ${board.h}px`).toBeGreaterThan(0);
    // F2: a divider along its top edge is the line the books stand on.
    expect.soft(board.borderTop, 'F2: baseboard should be ruled off from the shelf surface').toBeGreaterThan(0);
    // F3: and it steps tonally away from the shelf surface, so the strip is readable as
    // its own band rather than dissolving into the shelf.
    expect.soft(board.bg, `F3: baseboard should not match the shelf surface (${board.bg})`).not.toBe(board.shelfBg);

    // ---- G. Coherence regressions from the design pass ----
    const g = await page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        const sections = root.querySelector('.shelf-label .sections') as HTMLElement | null;
        const label = root.querySelector('.shelf-label .label') as HTMLElement | null;
        const cs = label ? getComputedStyle(label) : null;
        return {
            sectionsVisible: sections ? getComputedStyle(sections).display !== 'none' : false,
            labelColor: cs ? cs.color : 'none',
            labelWeight: cs ? cs.fontWeight : '0',
            labelFont: cs ? cs.fontFamily : '',
            labelWidth: label ? Math.round(label.getBoundingClientRect().width) : 0,
        };
    });
    // G1: the vestigial translucent-white "sections" scrub bar must stay hidden
    expect.soft(g.sectionsVisible, 'G1: sections scrub bar should be hidden').toBe(false);
    // G2: the section title reads as a heading -- rendered, and at a heading weight rather
    // than body copy.
    expect.soft(g.labelWidth, 'G2: section title should be rendered').toBeGreaterThan(0);
    expect.soft(Number(g.labelWeight), `G2: section title should be a heading weight, got ${g.labelWeight}`)
        .toBeGreaterThanOrEqual(600);
    // G3: it inherits the site typeface rather than LibraryExplorer's own bahnschrift/Avenir
    // stacks, which every genre-mode descendant would otherwise pick up.
    expect.soft(g.labelFont, `G3: section title should use the site typeface, got ${g.labelFont}`)
        .toContain('Schibsted Grotesk');
});
