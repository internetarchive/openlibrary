import { test, expect, Page } from "@playwright/test";
import { NavigationPage } from "../pages/NavigationPage";
import { BASE_URL, VALID_EMAIL, VALID_PASSWORD } from "../helper-config";
import { LoginPage } from "../pages/LoginPage";
import { BookPage } from "../pages/BookPage";

let navigationPage: NavigationPage;

test.beforeEach(async({page}: {page: Page}) => {
    navigationPage = new NavigationPage({page});
    await page.goto(BASE_URL);
});

test("navigate to my books page after login", async({page}: {page: Page}) => {
  const loginPage = await navigationPage.navigateToMyBooks() as LoginPage;
  await loginPage.login(VALID_EMAIL, VALID_PASSWORD);
  const booksPage = new BookPage({page});
  await expect(page).toHaveURL(BookPage.MY_BOOKS_URL);
  await expect(booksPage.booksDropdown).toBeVisible();
});

test("my books page after login", async({page}: {page: Page}) => {
  const loginPage = new LoginPage({page});
  await loginPage.navigate();
  await loginPage.login(VALID_EMAIL, VALID_PASSWORD);
  const booksPage = await navigationPage.navigateToMyBooks() as BookPage;
  await expect(page).toHaveURL(BookPage.MY_BOOKS_URL);
  await expect(booksPage.booksDropdown).toBeVisible();
});

test("clicking browse opens the dropdown menu", async({page}: {page: Page}) => {
    await navigationPage.navigateToBrowse();
    await expect(navigationPage.dropdownOnBrowse).toBeVisible();
    await expect(navigationPage.optionOnBrowseDropdown).toHaveText([
        'Subjects',
        'Trending',
        'Library Explorer',
        'Lists',
        'Collections',
        'K-12 Student Library',
        'Book Talks',
        'Random Book',
        'Advanced Search'
      ], { timeout: 5000 });
});