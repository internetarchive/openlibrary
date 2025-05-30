import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';
import { INVALID_EMAIL, VALID_EMAIL, VALID_PASSWORD } from '../helper-config';

test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage({ page });
    await loginPage.navigate();
    await loginPage.waitForLoad();
});

test('login with valid credentials', async ({ page }) => {
    const loginPage = new LoginPage({ page });
    const loggedInPage = await loginPage.login(VALID_EMAIL, VALID_PASSWORD);
    await loggedInPage.waitForLoad();
    await expect(loggedInPage.myAccountIcon).toBeVisible();
});

test('login with invalid email', async ({ page }) => {
    const loginPage = new LoginPage({ page });
    await loginPage.login(INVALID_EMAIL, '');
    expect(await loginPage.getEmailValidationMessage()).toContain(
        loginPage.emailInvalidMessage
    );
});
