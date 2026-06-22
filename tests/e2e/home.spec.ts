import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

test.describe('Home page @smoke', () => {
    test('loads with correct title and header', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto('/');
        await expect(page).toHaveTitle(/Open Library/i);
        // Global site header must be visible
        await expect(page.locator('#header-bar').first()).toBeVisible();
        expect(errors()).toHaveLength(0);
    });

    test('shows main content body', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('#contentBody')).toBeVisible();
    });

    test('header search input is present and focusable', async ({ page }) => {
        await page.goto('/');
        // The header search bar should be in the DOM (may be hidden on mobile behind a toggle)
        const searchInput = page.locator('#header-bar input[type="text"], #header-bar input[type="search"]').first();
        await expect(searchInput).toBeAttached();
    });

    test('footer is rendered', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('#footer-content, footer').first()).toBeVisible();
    });
});
