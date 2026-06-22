import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

const SUBJECT_URL = '/subjects/fiction';

// Subjects pages require Solr index data.
// In local dev with an empty Solr index they return 404; skip those tests gracefully.
const skipIfNoSolr = async ({ page }: { page: import('@playwright/test').Page }) => {
    const response = await page.goto(SUBJECT_URL);
    if (response?.status() === 404) {
        test.skip(true, 'Subjects require Solr data — not available in this environment');
    }
};

test.describe('Subjects page @smoke', () => {
    test('loads with subject heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        const response = await page.goto(SUBJECT_URL);
        test.skip(response?.status() === 404, 'Subjects require Solr data — not available in this environment');
        // h1.inline is the subject name heading (from subjects.html template)
        const heading = page.locator('h1.inline, h1').first();
        await expect(heading).toBeVisible();
        const text = await heading.textContent();
        expect(text?.trim().length).toBeGreaterThan(0);
        expect(errors()).toHaveLength(0);
    });

    test('shows book count for the subject', async ({ page }) => {
        await skipIfNoSolr({ page });
        // #coversCount shows the number of works with this subject
        const count = page.locator('#coversCount');
        await expect(count).toBeVisible();
    });

    test('renders the content body with works', async ({ page }) => {
        await skipIfNoSolr({ page });
        await expect(page.locator('.contentBody')).toBeVisible();
    });

    test('has a search form for books with this subject', async ({ page }) => {
        await skipIfNoSolr({ page });
        // subjects.html includes a search form bound to /search
        const form = page.locator('form[action="/search"]');
        await expect(form).toBeAttached();
    });

    test('unknown subject shows a page (not 500)', async ({ page }) => {
        const response = await page.goto('/subjects/xyzzy_nonexistent_subject_12345');
        expect(response?.status()).not.toBe(500);
        await expect(page.locator('#header-bar').first()).toBeVisible();
    });
});
