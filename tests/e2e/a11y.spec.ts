import { test, expect } from '@playwright/test';
import { a11yCheck, expectNoViolations, THIRD_PARTY_FRAMES } from './a11y';

test.describe('Accessibility @a11y', () => {
    test('home page has no WCAG 2.1 AA violations', async ({ page }) => {
        await page.goto('/');
        expectNoViolations(await a11yCheck(page, { exclude: THIRD_PARTY_FRAMES }));
    });

    test('home page passes colour contrast', async ({ page }) => {
        // The example of a scoped, single-rule check. Contrast is also the
        // headline reason this suite exists: the jsdom component tests can't
        // evaluate it at all, because jsdom never paints anything.
        await page.goto('/');
        expectNoViolations(await a11yCheck(page, { rules: ['color-contrast'], exclude: THIRD_PARTY_FRAMES }));
    });

    test('axe actually evaluates rules', async ({ page }) => {
        // Guard against a passing suite that checks nothing: a bad selector or
        // a broken tag filter would leave zero applicable rules, and every
        // "no violations" assertion above would be vacuously true.
        await page.goto('/');
        const results = await a11yCheck(page, { exclude: THIRD_PARTY_FRAMES });

        expect(results.testEngine.name).toBe('axe-core');
        expect(results.passes.length).toBeGreaterThan(20);
        expect(results.passes.map((rule) => rule.id)).toContain('color-contrast');
    });
});
