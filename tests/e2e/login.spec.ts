import { test, expect } from '@playwright/test';
import { collectConsoleErrors, login, E2E_EMAIL, E2E_PASSWORD } from './helpers';

test.describe('Login page @smoke', () => {
    test('loads with Log In heading', async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await page.goto('/account/login');
        // The hero title renders in the DOM on every viewport but is hidden by responsive
        // CSS on narrow (mobile) layouts, so assert it's attached rather than visible.
        const title = page.locator('h1.ol-signup-hero__title');
        await expect(title).toBeAttached();
        const heading = await title.textContent();
        expect(heading?.trim()).toMatch(/log in/i);
        expect(errors()).toHaveLength(0);
    });

    test('email and password inputs are present', async ({ page }) => {
        await page.goto('/account/login');
        await expect(page.locator('input[name="username"]')).toBeVisible();
        await expect(page.locator('input[name="password"]')).toBeVisible();
    });

    // FIXME: the FastAPI login route answers a failed form POST with
    // 400 {"detail": ...} (openlibrary/fastapi/account.py), so the browser gets
    // raw JSON instead of the login page carrying a flash error. This test
    // describes the behaviour to restore; drop the fixme once it is.
    test.fixme('wrong password shows an error and stays on the login page', async ({ page }) => {
        // The dev mock IA auth accepts any non-empty password except the
        // sentinel "bad_password" (docker/mockservices/main.py), so this is
        // the only wrong password that fails in both dev and production.
        await page.goto('/account/login');
        await page.fill('input[name="username"]', 'nobody@example.com');
        await page.fill('input[name="password"]', 'bad_password');
        await page.click('button[name="login"]');
        await expect(page.locator('#header-bar').first()).toBeVisible({ timeout: 10_000 });
        expect(new URL(page.url()).pathname).toBe('/account/login');
        await expect(page.locator('.flash-messages .error')).toBeVisible();
        // Still anonymous
        await expect(page.locator('#header-bar a[href="/account/login"]').first()).toBeAttached();
    });

    test('form login with valid credentials signs the patron in', async ({ page }) => {
        // The form authenticates against IA by email, unlike login.json. Reached
        // directly it posts an empty redirect, and the login route treats that as
        // "no redirect" and falls back to My Books (openlibrary/fastapi/account.py),
        // which then resolves to the patron's own /people/<user>/books.
        test.skip(!E2E_EMAIL, 'No credentials for this environment — set OL_E2E_EMAIL / OL_E2E_PASSWORD');
        const errors = collectConsoleErrors(page);
        await page.goto('/account/login');
        await page.fill('input[name="username"]', E2E_EMAIL);
        await page.fill('input[name="password"]', E2E_PASSWORD);
        await page.click('button[name="login"]');
        await page.waitForURL(/\/(account|people\/[^/]+)\/books/, { timeout: 10_000 });
        const header = page.locator('#header-bar').first();
        await expect(header).toBeVisible();
        await expect(header.locator('a[href="/account/books"]').first()).toBeAttached();
        expect(errors()).toHaveLength(0);
    });

    test('mobile: form fields are visible and not clipped @mobile', async ({ page }) => {
        await page.goto('/account/login');
        const emailInput = page.locator('input[name="username"]');
        await expect(emailInput).toBeVisible();
        const box = await emailInput.boundingBox();
        expect(box).not.toBeNull();
        // Input should be fully within the viewport horizontally
        const viewport = page.viewportSize();
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width + 1);
    });

    test.describe('when already logged in', () => {
        test.beforeEach(({ page }) => login(page));

        test('shows the already-logged-in notice instead of the form', async ({ page }) => {
            const errors = collectConsoleErrors(page);
            await page.goto('/account/login');
            await expect(page.locator('#contentBody')).toContainText(/already logged in/i);
            await expect(page.locator('input[name="username"]')).toHaveCount(0);
            // Guards the LOCAL_DEV credential autofill, which used to run
            // against a form that isn't rendered for logged-in users.
            expect(errors()).toHaveLength(0);
        });
    });
});
