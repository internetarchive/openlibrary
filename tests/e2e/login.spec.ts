import { test, expect } from '@playwright/test';
import { collectConsoleErrors } from './helpers';

test.describe('Login page @smoke', () => {
    test('loads with Log In heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto('/account/login');
        await expect(page.locator('h1.ol-signup-hero__title')).toBeVisible();
        const heading = await page.locator('h1.ol-signup-hero__title').textContent();
        expect(heading?.trim()).toMatch(/log in/i);
        expect(errors()).toHaveLength(0);
    });

    test('email and password inputs are present', async ({ page }) => {
        await page.goto('/account/login');
        await expect(page.locator('input[name="username"]')).toBeVisible();
        await expect(page.locator('input[name="password"]')).toBeVisible();
    });

    test('submit button is present and labeled', async ({ page }) => {
        await page.goto('/account/login');
        const btn = page.locator('button[name="login"]');
        await expect(btn).toBeVisible();
        const label = await btn.textContent();
        expect(label?.trim().length).toBeGreaterThan(0);
    });

    test('sign up link is present', async ({ page }) => {
        await page.goto('/account/login');
        const signupLink = page.locator('a[href="/account/create"]').first();
        await expect(signupLink).toBeAttached();
    });

    test('invalid credentials do not crash the page', async ({ page }) => {
        await page.goto('/account/login');
        await page.fill('input[name="username"]', 'nobody@example.com');
        await page.fill('input[name="password"]', 'wrongpassword123');
        await page.click('button[name="login"]');
        // Should stay on login-related page (not crash to 500)
        await expect(page.locator('#header-bar').first()).toBeVisible({ timeout: 10_000 });
        const status = page.url();
        // Should not redirect to a 500 page
        expect(status).not.toContain('500');
    });

    test('mobile: form fields are visible and not clipped', async ({ page, isMobile }) => {
        if (!isMobile) test.skip();
        await page.goto('/account/login');
        const emailInput = page.locator('input[name="username"]');
        await expect(emailInput).toBeVisible();
        const box = await emailInput.boundingBox();
        expect(box).not.toBeNull();
        // Input should be fully within the viewport horizontally
        const viewport = page.viewportSize();
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width + 1);
    });
});
