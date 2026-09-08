import { test, expect } from '@playwright/test';
import { collectConsoleErrors, login } from './helpers';

// OL286811W is present in the dev DB seed data; OL45883W is the production fallback
// Playwright follows the 301 redirect to the slug URL automatically
const WORK_URL = process.env.OL_BASE_URL?.startsWith('https')
    ? '/works/OL45883W'
    : '/works/OL286811W';

test.describe('Book (Work) page @smoke', () => {
    test('loads with a title in the heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto(WORK_URL);
        // h1.work-title exists in both mobile and desktop DOM; filter to the visible one
        const title = page.locator('h1.work-title').filter({ visible: true });
        await expect(title).toBeVisible();
        const titleText = await title.textContent();
        expect(titleText?.trim().length).toBeGreaterThan(0);
        expect(errors()).toHaveLength(0);
    });

    test('shows work details section', async ({ page }) => {
        await page.goto(WORK_URL);
        await expect(page.locator('.workDetails')).toBeVisible();
    });

    test('shelf button sends anonymous visitors to log in', async ({ page }) => {
        await page.goto(WORK_URL);
        const button = page.locator('ol-shelf-button[variant="split"]').first();
        await expect(button).toBeAttached();
        // No reader, so no popover: the trigger stands alone and a click goes to login.
        await expect(button).not.toHaveAttribute('user-key');
        await button.locator('.main').click();
        await page.waitForURL(/\/account\/login/);
        const url = new URL(page.url());
        expect(url.pathname).toBe('/account/login');
        // Back to the same book afterwards.
        expect(url.searchParams.get('redirect')).toMatch(/^\/works\/OL\d+W/);
    });

    test.describe('when logged in', () => {
        test.beforeEach(({ page }) => login(page));

        test('loads without console errors', async ({ page }) => {
            const errors = collectConsoleErrors(page);
            await page.goto(WORK_URL);
            await expect(page.locator('h1.work-title').filter({ visible: true })).toBeVisible();
            expect(errors()).toHaveLength(0);
        });

        test('shelf button is rendered for the reader', async ({ page }) => {
            await page.goto(WORK_URL);
            const button = page.locator('ol-shelf-button[variant="split"]').first();
            await expect(button).toBeAttached();
            // The server rendered the reader in, with their state, so nothing
            // is fetched after load and the popover is wired up.
            await expect(button).toHaveAttribute('user-key', /^\/people\/.+/);
            await expect(button).toHaveAttribute('data-hydrated');
            await expect(button.locator('ol-shelf-actions')).toBeAttached();
        });
    });

    test('mobile: work title is visible without horizontal scroll @mobile', async ({ page }) => {
        await page.goto(WORK_URL);
        const title = page.locator('h1.work-title').filter({ visible: true });
        await expect(title).toBeVisible();
        const box = await title.boundingBox();
        expect(box).not.toBeNull();
        // Title should not overflow the viewport width
        expect(box!.x).toBeGreaterThanOrEqual(0);
    });
});
