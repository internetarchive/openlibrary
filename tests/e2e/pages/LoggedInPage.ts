import { Page, Locator } from "@playwright/test";
export class LoggedInPage {
  page: Page;
  myAccountIcon: Locator;

  constructor({ page }: { page: Page }) {
    this.page = page;
    this.myAccountIcon = page.locator(".account__icon");
  }

  async waitForLoad() {
    await this.myAccountIcon.waitFor();
  }
}
