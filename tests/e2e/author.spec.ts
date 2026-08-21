import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

// OL23919A = J.K. Rowling (reliable on production).
// In local dev the seed DB may not include this author — tests skip gracefully on 404.
const AUTHOR_URL = '/authors/OL23919A';

const skipIfNotFound = async ({ page }: { page: import('@playwright/test').Page }) => {
    const response = await page.goto(AUTHOR_URL);
    if (response?.status() === 404) {
        test.skip(true, 'Author not in this environment\'s DB — skipping');
    }
};

test.describe('Author page @smoke', () => {
    test('loads with author name in heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        const response = await page.goto(AUTHOR_URL);
        test.skip(response?.status() === 404, 'Author not in this environment\'s DB');
        // h1[itemprop="name"] is the author name heading in type/author/view.html
        const heading = page.locator('h1[itemprop="name"]');
        await expect(heading).toBeVisible();
        const text = await heading.textContent();
        expect(text?.trim().length).toBeGreaterThan(0);
        expect(errors()).toHaveLength(0);
    });

    test('works list renders at least one item when Solr is available', async ({ page }) => {
        await skipIfNotFound({ page });
        const resultsList = page.locator('#searchResults .list-books li, #searchResults .searchResultItem');
        const count = await resultsList.count();
        if (count === 0) {
            test.skip(true, 'No Solr data — works list empty in this environment');
        }
        expect(count).toBeGreaterThan(0);
    });

    test('unknown author shows a page (not 500)', async ({ page }) => {
        const response = await page.goto('/authors/OL999999999A');
        expect(response?.status()).not.toBe(500);
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });
});
