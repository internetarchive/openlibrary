import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

// OL3421846M is present in the dev DB seed data (referenced in lists unit tests).
// OL7353617M is a known production edition (The Fellowship of the Ring).
const EDITION_URL = process.env.OL_BASE_URL?.startsWith('https')
    ? '/books/OL7353617M'
    : '/books/OL3421846M';

test.describe('Edition page @smoke', () => {
    test('loads with book title in heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        const response = await page.goto(EDITION_URL);
        test.skip(response?.status() === 404, 'Edition not in this environment\'s DB');
        // h1.work-title is the book title heading in type/edition/title_and_author.html
        const title = page.locator('h1.work-title').filter({ visible: true });
        await expect(title).toBeVisible();
        const text = await title.textContent();
        expect(text?.trim().length).toBeGreaterThan(0);
        expect(errors()).toHaveLength(0);
    });

    test('unknown edition shows a page (not 500)', async ({ page }) => {
        const response = await page.goto('/books/OL999999999M');
        expect(response?.status()).not.toBe(500);
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });
});
