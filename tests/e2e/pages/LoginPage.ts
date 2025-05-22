import { Page, Locator } from "@playwright/test";
import { BASE_URL } from "../helper-config";
import { LoggedInPage } from "./LoggedInPage";

export class LoginPage {
  page: Page;
  emailFieldLocator: Locator;
  passwordFieldLocator: Locator;
  loginButton: Locator;
  emailValidationLocator: Locator;
  emailInvalidMessage = "Please include an '@' in the email address.";
  static readonly LOGIN_URL = `${BASE_URL}/account/login`;

  constructor({ page }: { page: Page }) {
    this.page = page;
    this.emailFieldLocator = page.getByRole("textbox", { name: "Email" });
    this.passwordFieldLocator = page.getByText("Password", { exact: true });
    this.loginButton = page.getByRole("button", { name: "Log In" });
    this.emailValidationLocator = page.locator("input#username");
  }

  async waitForLoad() {
    await this.loginButton.waitFor();
  }

  async navigate() {
    await this.page.goto(LoginPage.LOGIN_URL);
  }

  async getEmailValidationMessage(): Promise<string> {
    return await this.emailValidationLocator.evaluate((element) => {
      const input = element as HTMLInputElement;
      return input.validationMessage;
    });
  }

  async login(email: string, password: string): Promise<LoggedInPage> {
    await this.emailFieldLocator.fill(email);
    await this.passwordFieldLocator.fill(password);
    await this.loginButton.click();
    return new LoggedInPage({ page: this.page });
  }
}
