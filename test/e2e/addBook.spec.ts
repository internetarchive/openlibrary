import { test, expect, Page } from "@playwright/test";
import { LoginPage } from "../pages/LoginPage";
import { VALID_EMAIL, VALID_PASSWORD } from "../helper-config";
import { AddBookPage } from "../pages/AddBookPage";

test.beforeEach(async ({ page }: { page: Page }) => {
  await page.goto(LoginPage.LOGIN_URL);
  const loginPage = new LoginPage({ page });
  await loginPage.login(VALID_EMAIL, VALID_PASSWORD);
});

test("add a new book", async ({ page }: { page: Page }) => {
  const TITLE: string = "One Piece4";
  const PUBLISHER: string = "Luffy and Zoro";
  const PUBLISHED: string = "1999";
  const addBookPage = new AddBookPage({ page });
  await addBookPage.navigate();
  await addBookPage.addBook(TITLE, PUBLISHER, PUBLISHED);
  await expect(addBookPage.moreInfoLocator).toBeVisible();
  await addBookPage.save();
  await expect(addBookPage.addedLocator).toBeVisible();
});