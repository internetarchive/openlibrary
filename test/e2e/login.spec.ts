import { test, expect, Page } from "@playwright/test";
import { LoginPage } from "../pages/LoginPage";
import { LOGIN_URL, INVALID_EMAIL, VALID_EMAIL, VALID_PASSWORD, } from "../helper-config";

test.beforeEach(async ({ page }) => {
  await page.goto(LOGIN_URL);
});

test("login with valid credentials", async ({ page }) => {
  const loginPage = new LoginPage({ page });
  await loginPage.navigate();
  await loginPage.login(VALID_EMAIL, VALID_PASSWORD);
  await page.getByAltText("My account").click();
  await expect(loginPage.logoutButton).toBeVisible();
});

test("login with invalid credentials", async ({ page }) => {
  const loginPage = new LoginPage({ page });
  await loginPage.navigate();
  await loginPage.login(INVALID_EMAIL, "");
  const validationMessage = await page
    .locator("input#username")
    .evaluate((element) => {
      const input = element as HTMLInputElement;
      return input.validationMessage;
    });
  await expect(validationMessage).toContain(loginPage.errorMessage);
});