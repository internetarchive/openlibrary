import { Locator, Page } from "@playwright/test"
import { BASE_URL } from "../helper-config";

export class BookPage {
    page: Page;
    booksDropdown: Locator;
    static readonly MY_BOOKS_URL: string = `${BASE_URL}/people/openlibrary/books`;

    constructor({page}: {page: Page}) {
        this.page = page;
        this.booksDropdown = page.locator('.disguised-select');
    }
}