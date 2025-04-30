import { test, expect, Page } from "@playwright/test";
import { LoginPage } from "../pages/LoginPage";
import { base_url, invalidEmail, validEmail, validPassword } from "../helper-config";

test.beforeEach(async ({ page }) => {
  await page.goto(base_url);
  const loginPage = new LoginPage({ page });
  await loginPage.navigateToLoginPage();
});

test("login with valid credentials", async ({ page }) => {
  const loginPage = new LoginPage({ page });
  await loginPage.login(validEmail, validPassword);
  await page.getByAltText("My account").click();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
});

test("login with invalid credentials", async ({ page }) => {
  const loginPage = new LoginPage({ page });
  await loginPage.login(invalidEmail, "");
  const validationMessage = await page
    .locator("input#username")
    .evaluate((element) => {
      const input = element as HTMLInputElement;
      return input.validationMessage;
    });
  expect(validationMessage).toContain(loginPage.errorMessage);
});
