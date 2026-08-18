import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

/**
 * <ol-button> form semantics that only a real browser can prove. jsdom has no
 * ElementInternals form association for a `<fieldset disabled>`, no implicit
 * submission (Enter in a text field), and no native validation UI, so
 * tests/unit/js/OLButton.test.js can't cover these. The fixture is the "Form
 * submission" demo on the design page:
 *
 *   <form id="demo-button-form">
 *     <fieldset id="demo-button-form-fieldset">
 *       <input id="demo-button-form-input" name="name" required>
 *       <input id="demo-button-form-input-2" name="nickname">
 *       <ol-button type="submit" name="action" value="save">Submit</ol-button>
 *       <ol-button type="reset">Reset</ol-button>
 *     </fieldset>
 *   </form>
 *   <ol-toggle id="demo-button-form-disable">   toggles fieldset.disabled
 *   #demo-button-form-output                    "<name> [<action>, via <label>]"
 *   #demo-button-form-count                     number of submit events
 */

const PAGE = '/developers/design/components';

const sel = {
    form: '#demo-button-form',
    fieldset: '#demo-button-form-fieldset',
    name: '#demo-button-form-input',
    nickname: '#demo-button-form-input-2',
    // `.control` is the visible <button> in the shadow root; Playwright's CSS
    // engine pierces open shadow roots (even for `>`); the light-DOM proxy is
    // the only button carrying a `slot` attribute.
    submit: '#demo-button-form ol-button[type="submit"]',
    submitControl: '#demo-button-form ol-button[type="submit"] .control',
    resetControl: '#demo-button-form ol-button[type="reset"] .control',
    disableToggle: '#demo-button-form-disable .toggle',
    output: '#demo-button-form-output',
    count: '#demo-button-form-count',
};

async function gotoFixture(page: Page): Promise<void> {
    await page.route('https://archive.org/**', (route) => route.abort());
    await page.goto(PAGE);
    await expect(page.locator('#header-bar').first()).toBeVisible();
    await page.waitForFunction(() => customElements.get('ol-button') && customElements.get('ol-toggle'));
    await page.locator(sel.form).scrollIntoViewIfNeeded();
    // The submit button's light-DOM proxy is what makes the form semantics native.
    await expect(page.locator(`${sel.submit} button[slot][type="submit"]`)).toBeAttached();
}

test.describe('ol-button form semantics', () => {
    test.beforeEach(async ({ page }) => {
        await gotoFixture(page);
    });

    test('click submits with the button as submitter, carrying its name/value', async ({ page }) => {
        await page.fill(sel.name, 'Ada');
        await page.click(sel.submitControl);
        await expect(page.locator(sel.count)).toHaveText('1');
        await expect(page.locator(sel.output)).toHaveText('Ada [save, via Submit]');
    });

    test('Enter in a text field submits (implicit submission), even with several text fields', async ({ page }) => {
        // Two text inputs: without a real submit button in the form, the
        // browser would do nothing here.
        await page.fill(sel.name, 'Ada');
        await page.fill(sel.nickname, 'A');
        await page.locator(sel.nickname).press('Enter');
        await expect(page.locator(sel.count)).toHaveText('1');
        await expect(page.locator(sel.output)).toHaveText('Ada [save, via Submit]');
    });

    test('native validation runs: a required empty field blocks submission', async ({ page }) => {
        await page.fill(sel.name, '');
        await page.click(sel.submitControl);
        await page.locator(sel.nickname).press('Enter');
        // Give a wrongly-forwarded submit time to land.
        await page.waitForTimeout(100);
        await expect(page.locator(sel.count)).toHaveText('0');
        expect(await page.locator(sel.name).evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
    });

    test('preventDefault() on an ancestor click listener cancels the submit', async ({ page }) => {
        await page.evaluate((formSel) => {
            document.querySelector(formSel)!.addEventListener('click', (e) => e.preventDefault());
        }, sel.form);
        await page.fill(sel.name, 'Ada');
        await page.click(sel.submitControl);
        await page.waitForTimeout(100);
        await expect(page.locator(sel.count)).toHaveText('0');
    });

    test('type="reset" resets the form', async ({ page }) => {
        await page.fill(sel.name, 'Ada');
        await page.click(sel.submitControl);
        await expect(page.locator(sel.output)).toHaveText('Ada [save, via Submit]');
        await page.click(sel.resetControl);
        await expect(page.locator(sel.name)).toHaveValue('');
        await expect(page.locator(sel.output)).toHaveText('—');
    });

    test('a disabled fieldset disables the button, and re-enabling the fieldset re-enables it', async ({ page }) => {
        const control = page.locator(sel.submitControl);
        const disabledState = () => page.locator(sel.submit).evaluate((el) => ({
            matchesDisabled: el.matches(':disabled'),
            hasDisabledAttr: el.hasAttribute('disabled'),
        }));

        await page.click(sel.disableToggle);
        await expect(control).toBeDisabled();
        // Disabled by the fieldset only — the host must NOT grow its own
        // disabled attribute, or the fieldset could never re-enable it.
        expect(await disabledState()).toEqual({ matchesDisabled: true, hasDisabledAttr: false });

        // The proxy is disabled too, so the browser has no default button to
        // fire for implicit submission (the inputs are disabled as well).
        expect(await page.locator(`${sel.submit} button[slot]`).evaluate((el: HTMLButtonElement) => el.disabled)).toBe(true);
        await page.click(sel.submitControl, { force: true }).catch(() => undefined);
        await page.waitForTimeout(100);
        await expect(page.locator(sel.count)).toHaveText('0');

        await page.click(sel.disableToggle);
        await expect(control).toBeEnabled();
        expect(await disabledState()).toEqual({ matchesDisabled: false, hasDisabledAttr: false });
        await page.fill(sel.name, 'Ada');
        await page.locator(sel.name).press('Enter');
        await expect(page.locator(sel.count)).toHaveText('1');
    });

    test('loading blocks both click and Enter', async ({ page }) => {
        await page.fill(sel.name, 'Ada');
        await page.locator(sel.submit).evaluate((el: any) => { el.loading = true; });
        await page.click(sel.submitControl, { force: true }).catch(() => undefined);
        await page.locator(sel.name).press('Enter');
        await page.waitForTimeout(100);
        await expect(page.locator(sel.count)).toHaveText('0');
        await page.locator(sel.submit).evaluate((el: any) => { el.loading = false; });
        await page.locator(sel.name).press('Enter');
        await expect(page.locator(sel.count)).toHaveText('1');
    });

    test('the proxy is invisible and does not change the accessible label', async ({ page }) => {
        const info = await page.locator(sel.submit).evaluate((el) => {
            const proxy = el.querySelector(':scope > button') as HTMLButtonElement;
            return {
                rendered: proxy.getClientRects().length > 0,
                slotted: proxy.assignedSlot !== null,
                text: el.textContent!.trim(),
            };
        });
        expect(info).toEqual({ rendered: false, slotted: false, text: 'Submit' });
        await expect(page.locator(sel.submitControl)).toHaveAccessibleName('Submit');
    });
});

test.describe('FormAssociatedMixin fieldset handling', () => {
    test('ol-toggle inside a fieldset re-enables when the fieldset does', async ({ page }) => {
        await gotoFixture(page);
        // Same bug class as ol-button, in the shared mixin: an ancestor
        // fieldset toggle must round-trip. Built ad hoc since the design page
        // has no fieldset-wrapped toggle.
        const result = await page.evaluate(async () => {
            const wrap = document.createElement('div');
            wrap.innerHTML = '<form><fieldset><ol-toggle name="t">T</ol-toggle></fieldset></form>';
            document.body.appendChild(wrap);
            const fieldset = wrap.querySelector('fieldset')!;
            const toggle = wrap.querySelector('ol-toggle') as any;
            await toggle.updateComplete;
            const inner = () => (toggle.shadowRoot.querySelector('button') as HTMLButtonElement).disabled;
            fieldset.disabled = true;
            await toggle.updateComplete;
            const whileDisabled = { inner: inner(), attr: toggle.hasAttribute('disabled') };
            fieldset.disabled = false;
            await toggle.updateComplete;
            const afterEnabled = { inner: inner(), attr: toggle.hasAttribute('disabled') };
            wrap.remove();
            return { whileDisabled, afterEnabled };
        });
        expect(result).toEqual({
            whileDisabled: { inner: true, attr: false },
            afterEnabled: { inner: false, attr: false },
        });
    });
});
