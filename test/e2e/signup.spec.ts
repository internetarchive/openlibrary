import { test, expect } from "@playwright/test";
import { SignupPage } from "../pages/SignupPage";
import { BASE_URL, VALID_EMAIL, VALID_PASSWORD } from "../helper-config";

test.beforeEach(async ({ page }) => {
  await page.goto(BASE_URL);
});

test("signup", async ({ page }) => {
  const signup = new SignupPage({ page });
  await signup.signup(VALID_EMAIL, "Luffy", VALID_PASSWORD);
});