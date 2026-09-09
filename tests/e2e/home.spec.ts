import { test, expect } from '@playwright/test';
import { collectConsoleErrors, login } from './helpers';

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

    test('header offers Log In / Sign Up to anonymous visitors', async ({ page }) => {
        await page.goto('/');
        const header = page.locator('#header-bar').first();
        await expect(header.locator('a[href="/account/login"]').first()).toBeAttached();
        await expect(header.locator('a[href="/account/create"]').first()).toBeAttached();
        await expect(header.locator('a[href="/account"]')).toHaveCount(0);
    });

    test.describe('when logged in', () => {
        test.beforeEach(({ page }) => login(page));

        test('loads without console errors', async ({ page }) => {
            const errors = collectConsoleErrors(page);
            await page.goto('/');
            await expect(page.locator('#header-bar').first()).toBeVisible();
            expect(errors()).toHaveLength(0);
        });

        test('header shows the account menu instead of Log In', async ({ page }) => {
            await page.goto('/');
            const header = page.locator('#header-bar').first();
            await expect(header.locator('a[href="/account"]').first()).toBeAttached();
            await expect(header.locator('a[href="/account/login"]')).toHaveCount(0);
            await expect(header.locator('a[href="/account/create"]')).toHaveCount(0);
        });
    });
});
