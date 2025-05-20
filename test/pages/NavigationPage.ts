import { Locator, Page } from "@playwright/test"
import { LoginPage } from "./LoginPage";
import { BookPage } from "./BookPage";

export class NavigationPage {
    page : Page;
    loginPage: LoginPage;
    myBooksLink: Locator;
    browseLink: Locator;
    dropdownOnBrowse: Locator;
    optionOnBrowseDropdown: Locator;

    constructor({page}: {page: Page}) {
        this.page = page;
        this.myBooksLink = page.getByRole('link', {name: 'My Books'});
        this.browseLink = page.locator('#header-bar .browse-component details > summary');
        this.dropdownOnBrowse = page.locator('#header-bar .browse-dropdown-component .browse-dropdown-menu');
        this.optionOnBrowseDropdown = page.locator('#header-bar .browse-dropdown-component .browse-dropdown-menu li');
        }

    async navigateToMyBooks(): Promise<LoginPage | BookPage> {
        const loginPage = new LoginPage({page: this.page});
        await this.myBooksLink.click();
         const currentURL = this.page.url();
            if (currentURL.includes(LoginPage.LOGIN_URL)) {
                return new LoginPage({page: this.page});
            } else {
                return new BookPage({page: this.page});
            }
    }

    async navigateToBrowse() {
        await this.browseLink.click();
    }
}