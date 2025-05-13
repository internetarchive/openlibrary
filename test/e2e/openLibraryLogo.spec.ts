import { test, expect, Page } from "@playwright/test";
import { OpenLibraryLogo } from "../pages/OpenLibraryLogo";
import { BASE_URL } from "../helper-config";

let openLibraryLogoPage: OpenLibraryLogo;

test.beforeEach(async({ page }: {page: Page}) => {
    openLibraryLogoPage = new OpenLibraryLogo({page});
    await openLibraryLogoPage.navigateToHome();
});

test("open-library logo is visible", async({page}: {page: Page}) => {
    expect (openLibraryLogoPage.openLibraryLogo).toBeVisible;
    expect (openLibraryLogoPage.openLibraryLogoAltText).toBeVisible;
});

test("open-library logo click redirects to base URL", async({page}: {page: Page}) => {
    await openLibraryLogoPage.click();
    await expect(page).toHaveURL(BASE_URL);
});

test("tooltip appears on hovering over open-library logo", async({page}: {page: Page}) => {
    await openLibraryLogoPage.hover();
    expect (openLibraryLogoPage.openLibraryLogoTooltip).toBeVisible;
});


