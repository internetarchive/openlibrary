import { test,expect } from "@playwright/test";

const home_url="http://localhost:8080/"

test.beforeEach(async ({page})=>{
    await page.goto(home_url)
})

test('login with valid credentials', async ({page})=>{
    await page.locator(`//li[@class="hide-me"]/a[@href="/account/login"]`).click()
    await page.locator('//input[@id="username"]').fill('')
    await page.locator('//input[@id="username"]').fill('openlibrary@example.com')
    await page.locator('//input[@id="password"]').fill('')
    await page.locator('//input[@id="password"]').fill('admin123')
    await page.locator('//button[@title="Log In"]').click()
    await page.locator('//img[@class="account__icon"]').click()
    await expect(page.locator(`//button[@data-ol-link-track="Hamburger|Logout"]`)).toBeVisible()
})