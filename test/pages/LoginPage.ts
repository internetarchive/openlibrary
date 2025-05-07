import { Page, Locator } from "@playwright/test";

export class LoginPage {
  page: Page;
  loginLinkLocator: Locator;
  emailFieldLocator: Locator;
  passwordFieldLocator: Locator;
  loginButton: Locator;
  errorMessage = "Please include an '@' in the email address.";
  logoutButton: Locator;

  constructor({ page }: { page: Page }) {
    this.page = page;
    this.loginLinkLocator = page.getByRole("link", { name: "Log In" });
    this.emailFieldLocator = page.getByRole("textbox", { name: "Email" });
    this.passwordFieldLocator = page.getByText("Password", { exact: true });
    this.loginButton = page.getByRole("button", { name: "Log In" });
    this.logoutButton = page.getByRole("button", { name: "Log out" });
  }

  async waitForLoad() {
    await this.loginButton.waitFor();
  }

  async navigate(): Promise<void> {
    await this.loginLinkLocator.click();
  }

  async login(email: string, password: string) {
    await this.emailFieldLocator.fill(email);
    await this.passwordFieldLocator.fill(password);
    await this.loginButton.click();
  }
}