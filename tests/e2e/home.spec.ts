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

    test('header search trigger is present', async ({ page }) => {
        await page.goto('/');
        // The search bar is a Lit web component — the visible affordance is a trigger button
        // that opens a search dialog; there is no plain <input> in the DOM until the dialog opens.
        const searchTrigger = page.locator('.search-bar-component, button.search-bar-trigger').first();
        await expect(searchTrigger).toBeAttached();
    });
});
