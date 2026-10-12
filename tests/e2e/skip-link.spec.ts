import { test, expect } from '@playwright/test';

// WCAG 2.4.1 Bypass Blocks: the first Tab reaches a link that jumps past the header.
test.describe('Skip link @a11y', () => {
    test.beforeEach(async ({ page }) => {
        // Block archive.org so the donation banner can't take the first Tab stop.
        await page.route('https://archive.org/**', (route) => route.abort());
        await page.goto('/');
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });

    test('is off-screen until focused, then visible', async ({ page }) => {
        const skipLink = page.locator('.skip-link');
        await expect(skipLink).not.toBeInViewport();

        await page.keyboard.press('Tab');
        await expect(skipLink).toBeFocused();
        await expect(skipLink).toBeInViewport();
    });

    test('moves focus past the header into main', async ({ page }) => {
        await page.keyboard.press('Tab');
        await page.keyboard.press('Enter');
        await expect(page.locator('main#test-body-mobile')).toBeFocused();

        // The next Tab stop is inside main, not back in the header.
        await page.keyboard.press('Tab');
        const inMain = await page.evaluate(() => !!document.activeElement?.closest('main#test-body-mobile'));
        expect(inMain).toBe(true);
    });
});
