import { test, expect } from "@playwright/test";
import { SignupPage } from "../pages/SignupPage";
import { base_url, validEmail, validPassword } from "../helper-config";

test.beforeEach(async ({ page }) => {
  await page.goto(base_url);
});

test("signup", async ({ page }) => {
  const signup = new SignupPage({ page });
  await signup.signup(validEmail, "Luffy", validPassword);
});
