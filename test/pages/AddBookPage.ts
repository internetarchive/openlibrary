import { Locator, Page } from "@playwright/test";

export class AddBookPage {
  page: Page;
  profileIcon: Locator;
  addBookLink: Locator;
  titleLocator: Locator;
  publisherLocator: Locator;
  publishedLocator: Locator;
  addButton: Locator;
  saveButton: Locator;
  moreInfoLocator: Locator;
  addedLocator:Locator

  constructor({ page }: { page: Page }) {
    this.page = page;
    this.titleLocator = page.getByRole("textbox", { name: "Title" });
    this.publisherLocator = page.getByRole("textbox", {
      name: "Who is the publisher",
    });
    this.publishedLocator = page.getByRole("textbox", {
      name: "When was it published?",
    });
    this.addButton = page.getByRole("button", { name: "Add" });
    this.profileIcon = page.getByAltText("My account");
    this.addBookLink = page.locator(
      `a[data-ol-link-track="Hamburger|AddBook"]`
    );
    this.saveButton = page.getByRole("button", { name: "Save" });
    this.moreInfoLocator = page.getByText(
      "Thank you for adding that book! Any more information you could provide would be wonderful!",
      { exact: true }
    );
    this.addedLocator= page.getByText("Thank you very much for adding that new book!")

  }

  async navigate() {
    await this.profileIcon.click();
    await this.addBookLink.click();
  }

  async addBook(title: string, publisher: string, published: string) {
    await this.titleLocator.fill(title);
    await this.publisherLocator.fill(publisher);
    await this.publishedLocator.fill(published);
    await this.addButton.click();
  }

  async save() {
    await this.saveButton.click();
  }
}