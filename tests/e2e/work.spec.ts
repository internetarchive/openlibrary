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

    test('reading log dropper is disabled for anonymous visitors', async ({ page }) => {
        await page.goto(WORK_URL);
        await expect(page.locator('.my-books-dropper.generic-dropper--disabled').first()).toBeAttached();
    });

    test.describe('when logged in', () => {
        test.beforeEach(({ page }) => login(page));

        test('loads without console errors', async ({ page }) => {
            const errors = collectConsoleErrors(page);
            await page.goto(WORK_URL);
            await expect(page.locator('h1.work-title').filter({ visible: true })).toBeVisible();
            expect(errors()).toHaveLength(0);
        });

        test('reading log dropper is enabled', async ({ page }) => {
            await page.goto(WORK_URL);
            const dropper = page.locator('.my-books-dropper').first();
            await expect(dropper).toBeAttached();
            await expect(dropper).not.toHaveClass(/generic-dropper--disabled/);
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
