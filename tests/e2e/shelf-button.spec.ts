import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { a11yCheck, expectNoViolations } from './a11y';
import { collectConsoleErrors, login } from './helpers';

/**
 * <ol-shelf-button> against the real server: what the jsdom suites cannot
 * prove. A click on the book page reaches the reading log and the page
 * reopens on that shelf; carousel buttons rendered without a reader get
 * their state from one ReadingState.json request.
 */

// A work of this spec's own, since it changes the reader's shelves while other
// specs scan theirs in parallel. OL20600W is in the dev seed; OL27448W is prod.
const WORK_URL = process.env.OL_BASE_URL?.startsWith('https')
    ? '/works/OL27448W'
    : '/works/OL20600W';
const WORK_OLID = WORK_URL.split('/').pop()!;

const WANT_TO_READ = '1';

/** Take a work off whatever shelf it is on. */
async function clearShelf(page: Page, olid: string): Promise<void> {
    const response = await page.request.post(`/works/${olid}/bookshelves.json`, {
        form: { bookshelf_id: '-1' },
    });
    expect(response.ok(), `could not clear ${olid}: ${await response.text()}`).toBe(true);
}

test.describe('ol-shelf-button', () => {
    test.describe('when logged in', () => {
        test.beforeEach(async ({ page }) => {
            await login(page);
            await clearShelf(page, WORK_OLID);
        });

        test.afterEach(async ({ page }) => {
            await clearShelf(page, WORK_OLID);
        });

        test('book page: a click shelves the book and the page reopens on that shelf', async ({ page }) => {
            const errors = collectConsoleErrors(page);
            await page.goto(WORK_URL);
            const button = page.locator('ol-shelf-button[variant="split"]').first();
            const main = button.locator('.main');
            await expect(button).not.toHaveAttribute('shelf');
            await expect(main).toHaveAttribute('aria-pressed', 'false');

            const saved = page.waitForResponse((r) =>
                r.url().includes(`/works/${WORK_OLID}/bookshelves.json`) && r.request().method() === 'POST');
            await main.click();
            expect((await saved).ok()).toBe(true);

            // The button reports the change and the page hands it back down.
            await expect(button).toHaveAttribute('shelf', WANT_TO_READ);
            await expect(main).toHaveAttribute('aria-pressed', 'true');
            // The split's own live region, not the popover's.
            await expect(button.locator('.split > [role="status"]')).toContainText(/Want to Read/);

            // Rendered in by the server this time: no fetch, no flash.
            await page.reload();
            const again = page.locator('ol-shelf-button[variant="split"]').first();
            await expect(again).toHaveAttribute('shelf', WANT_TO_READ);
            await expect(again).toHaveAttribute('data-hydrated');
            await expect(again.locator('.main')).toHaveAttribute('aria-pressed', 'true');
            expect(errors()).toHaveLength(0);
        });

        test('book page: clicking again takes it back off', async ({ page }) => {
            await page.goto(WORK_URL);
            const button = page.locator('ol-shelf-button[variant="split"]').first();
            const main = button.locator('.main');
            await main.click();
            await expect(button).toHaveAttribute('shelf', WANT_TO_READ);
            await main.click();
            await expect(button).not.toHaveAttribute('shelf');
            await page.reload();
            await expect(page.locator('ol-shelf-button[variant="split"]').first()).not.toHaveAttribute('shelf');
        });

        test('book page: the click that closes the menu does not land on the page beneath', async ({ page }) => {
            // The popover sets block-outside-clicks; only a real browser can prove the hit-testing.
            await page.goto(WORK_URL);
            const button = page.locator('ol-shelf-button[variant="split"]').first();
            await expect(button.locator('ol-shelf-actions')).toBeAttached();
            await button.locator('.more').click();
            await expect(button).toHaveAttribute('open');

            // A click on the logo link closes the menu but stays on this page.
            const logo = page.locator('.logo-component a[href="/"]');
            const box = (await logo.boundingBox())!;
            await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);

            await expect(button).not.toHaveAttribute('open');
            await expect(page).toHaveURL(new RegExp(`${WORK_URL}\\b`));

            // With the guard gone, the same click follows the link.
            await logo.click();
            await expect(page).toHaveURL(/\/$/);
        });
    });

    test.describe('carousel hydration', () => {
        // Home-page carousel cards are cached across readers, so they arrive without
        // a user key or state. Solr has to be up for a carousel to have cards at all.
        const CAROUSEL_BUTTON = '.book-cover-wrapper > ol-shelf-button[variant="icon"]';

        test('anonymous: carousel buttons render, and nothing is fetched', async ({ page }) => {
            const stateRequests: string[] = [];
            page.on('request', (r) => { if (r.url().includes('/partials/ReadingState.json')) stateRequests.push(r.url()); });
            await page.goto('/');
            const button = page.locator(CAROUSEL_BUTTON).first();
            await expect(button).toBeAttached({ timeout: 15_000 });
            await expect(button).not.toHaveAttribute('user-key');
            await expect(button).not.toHaveAttribute('data-hydrated');
            expect(stateRequests).toHaveLength(0);
        });

        test('buttons in off-screen slides are inert, so a hidden slide holds nothing focusable', async ({ page }) => {
            await page.route('https://archive.org/**', (route) => route.abort());
            await page.goto('/');
            const hidden = page.locator(`.slick-slide[aria-hidden="true"] ${CAROUSEL_BUTTON}`).first();
            const shown = page.locator(`.slick-slide[aria-hidden="false"] ${CAROUSEL_BUTTON}`).first();
            await expect(hidden).toBeAttached({ timeout: 15_000 });
            await expect(hidden).toHaveAttribute('inert');
            await expect(shown).not.toHaveAttribute('inert');
            // The rule the a11y suite would trip on if the sync were missing.
            expectNoViolations(await a11yCheck(page, { rules: ['aria-hidden-focus'] }));
        });

        test.describe('when logged in', () => {
            let olid = '';

            test.beforeEach(({ page }) => login(page));

            test.afterEach(async ({ page }) => {
                if (olid) await clearShelf(page, olid);
            });

            test('one batched request fills in the reader and their shelves', async ({ page }) => {
                const errors = collectConsoleErrors(page);
                const firstFetch = page.waitForResponse((r) => r.url().includes('/partials/ReadingState.json'));
                await page.goto('/');
                const response = await firstFetch;
                expect(response.ok()).toBe(true);

                const button = page.locator(CAROUSEL_BUTTON).first();
                await expect(button).toBeAttached();
                await expect(button).toHaveAttribute('data-hydrated');
                // The reader's key comes from <body data-user-key>, as a property.
                const userKey = await page.locator('body').getAttribute('data-user-key');
                expect(userKey).toMatch(/^\/people\//);
                await expect.poll(() => button.evaluate((el: any) => el.userKey)).toBe(userKey);
                await expect(button.locator('ol-shelf-actions')).toBeAttached();

                // That request asked for this card's work.
                olid = (await button.getAttribute('work-key'))!.split('/').pop()!;
                const asked = new URL(response.url()).searchParams.get('work_ids')!.split(',');
                expect(asked).toContain(olid);

                // Shelve it behind the page's back; the next load draws it shelved.
                await clearShelf(page, olid);
                const shelved = await page.request.post(`/works/${olid}/bookshelves.json`, {
                    form: { bookshelf_id: WANT_TO_READ },
                });
                expect(shelved.ok()).toBe(true);

                await page.reload();
                const again = page.locator(`ol-shelf-button[variant="icon"][work-key="/works/${olid}"]`).first();
                await expect(again).toHaveAttribute('shelf', WANT_TO_READ, { timeout: 15_000 });
                await expect(again.locator('.save')).toHaveAttribute('aria-label', /is on your reading log/);
                expect(errors()).toHaveLength(0);
            });
        });
    });
});
