import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

const SEARCH_URL = '/search?q=tolkien';

// Helper: skip if this environment has no Solr data (empty results page)
const skipIfNoSolrData = async ({ page }: { page: import('@playwright/test').Page }) => {
    await page.goto(SEARCH_URL);
    const title = await page.title();
    if (!title.toLowerCase().includes('tolkien')) {
        test.skip(true, 'No Solr data indexed in this environment — search results unavailable');
    }
};

test.describe('Search page @smoke', () => {
    test('loads results for a known query', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto(SEARCH_URL);
        test.skip(!(await page.title()).toLowerCase().includes('tolkien'), 'No Solr data indexed in this environment');
        // Result list must appear
        await expect(page.locator('.search-results, #searchResults').first()).toBeVisible();
        expect(errors()).toHaveLength(0);
    });

    test('shows at least one result item', async ({ page }) => {
        await skipIfNoSolrData({ page });
        await page.locator('.searchResultItem, .search-result-item').first().waitFor({ timeout: 10_000 });
        const count = await page.locator('.searchResultItem, .search-result-item').count();
        expect(count).toBeGreaterThan(0);
    });

    test('empty query shows no error page', async ({ page }) => {
        const response = await page.goto('/search?q=');
        expect(response?.status()).not.toBe(500);
        // Should not crash — either redirect to home or show empty state
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });
});
