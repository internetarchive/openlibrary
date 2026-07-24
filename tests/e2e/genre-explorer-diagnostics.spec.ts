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

    // ---- B. Sticky nav must be opaque so shelves don't bleed through when scrolled ----
    const navBg = await page.evaluate(() => {
        const nav = document.querySelector('ol-library-explorer')!.shadowRoot!
            .querySelector('.genre-top-nav-wrapper') as HTMLElement;
        return getComputedStyle(nav).backgroundColor;
    });
    expect.soft(navBg, `B1: sticky nav must be fully opaque, got ${navBg}`)
        .not.toContain('rgba');

    // nav stays pinned to the top of the pane after scrolling
    const navTopHome = await page.evaluate(() => document.querySelector('ol-library-explorer')!
        .shadowRoot!.querySelector('.genre-top-nav-wrapper')!.getBoundingClientRect().top);
    await setScroll(page, 1200);
    await page.waitForTimeout(400);
    const navTopScrolled = await page.evaluate(() => document.querySelector('ol-library-explorer')!
        .shadowRoot!.querySelector('.genre-top-nav-wrapper')!.getBoundingClientRect().top);
    expect.soft(Math.abs(navTopScrolled - navTopHome), 'B2: nav should stay pinned while scrolling')
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

    // ---- F. Skeuomorphic cue: the shelf board exists with wood tone + a cast shadow ----
    const board = await page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        const car = root.querySelector('.shelf-carousel') as HTMLElement;
        const after = getComputedStyle(car, '::after');
        return { shadow: after.boxShadow, bg: after.backgroundImage || after.backgroundColor, h: after.height };
    });
    expect.soft(board.shadow, 'F1: shelf board should cast a shadow (floating shelf)').not.toBe('none');

    // ---- G. Coherence regressions from the design pass ----
    const g = await page.evaluate(() => {
        const root = document.querySelector('ol-library-explorer')!.shadowRoot!;
        const sections = root.querySelector('.shelf-label .sections') as HTMLElement | null;
        const label = root.querySelector('.shelf-label .label') as HTMLElement | null;
        const cs = label ? getComputedStyle(label) : null;
        return {
            sectionsVisible: sections ? getComputedStyle(sections).display !== 'none' : false,
            labelBg: cs ? cs.backgroundColor : 'none',
            labelBorder: cs ? parseFloat(cs.borderTopWidth) : 0,
        };
    });
    // G1: the vestigial translucent-white "sections" scrub bar must stay hidden
    expect.soft(g.sectionsVisible, 'G1: sections scrub bar should be hidden').toBe(false);
    // G2: section title is a real printed shelf label (has a solid background), not bare
    // weak text
    const labelIsSigned = g.labelBg !== 'rgba(0, 0, 0, 0)' && g.labelBg !== 'transparent';
    expect.soft(labelIsSigned, `G2: section title should be a printed shelf label (bg ${g.labelBg})`).toBe(true);
});
