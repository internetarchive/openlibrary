import { test, expect } from '@playwright/test';
import { collectConsoleErrors, login } from './helpers';

test.describe('My Books @smoke', () => {
    test('redirects anonymous visitors to log in', async ({ page }) => {
        await page.goto('/account/books');
        const url = new URL(page.url());
        expect(url.pathname).toBe('/account/login');
        expect(url.searchParams.get('redirect')).toBe('/account/books');
    });

    test.describe('when logged in', () => {
        test.beforeEach(({ page }) => login(page));

        test('loads the patron\'s books page', async ({ page }) => {
            const errors = collectConsoleErrors(page);
            const response = await page.goto('/account/books');
            expect(response?.status()).toBe(200);
            expect(new URL(page.url()).pathname).toMatch(/^\/people\/[^/]+\/books$/);
            await expect(page.locator('#header-bar').first()).toBeVisible();
            // The My Books sidebar links each reading-log shelf.
            await expect(page.locator('.mybooks-menu a[href$="/books/want-to-read"]').first()).toBeVisible();
            expect(errors()).toHaveLength(0);
        });

        test('reading log shelves load', async ({ page }) => {
            for (const shelf of ['want-to-read', 'currently-reading', 'already-read']) {
                const response = await page.goto(`/account/books/${shelf}`);
                expect(response?.status(), shelf).toBe(200);
                await expect(page.locator('#header-bar').first()).toBeVisible();
            }
        });
    });
});
