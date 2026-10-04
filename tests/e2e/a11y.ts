import AxeBuilder from '@axe-core/playwright';
import { expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import type { AxeResults, Result } from 'axe-core';

/**
 * Shared axe-core setup for page-level accessibility tests.
 *
 * These run in a real browser, so unlike the jsdom component tests in
 * `openlibrary/components/__tests__/` they can see rendered pixels: colour
 * contrast, focus styling, and anything else that needs layout.
 *
 * Usage — scan a whole page against WCAG 2.1 AA:
 *
 *   const results = await a11yCheck(page);
 *   expectNoViolations(results);
 *
 * Usage — assert one rule, which is the pattern for a11y fix PRs. Scoping to
 * the rule you fixed keeps the test green while unrelated violations are still
 * outstanding elsewhere on the page:
 *
 *   test('iframes have accessible titles', async ({ page }) => {
 *       await page.goto('/');
 *       expectNoViolations(await a11yCheck(page, { rules: ['frame-title'] }));
 *   });
 */

/** WCAG 2.1 AA, which is Open Library's conformance target. */
const WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/**
 * Third-party iframes we embed but don't author, so their violations aren't
 * ours to fix. Axe does scan inside cross-origin frames under Playwright
 * (injection happens over the devtools protocol, not from the page), so
 * without this an embed like the archive.org donation banner — whose content
 * rotates by campaign, some variants failing `image-alt` — would tie a scan's
 * result to whatever a third party serves that day.
 *
 * Pass this explicitly rather than defaulting to it, so a test that skips
 * part of the page says so in its own body.
 */
export const THIRD_PARTY_FRAMES = ['iframe'];

export type A11yCheckOptions = {
    /** Limit the scan to these rule ids. Everything else is skipped. */
    rules?: string[];
    /** CSS selector to scan. Defaults to the whole page. */
    include?: string;
    /** CSS selectors to leave out, e.g. third-party embeds we don't control. */
    exclude?: string[];
    /** Rule ids to skip. Prefer `rules` for fix-PR tests. */
    disableRules?: string[];
};

/**
 * Run axe against the current page.
 *
 * Note this deliberately does not assert: callers decide whether to fail on
 * violations or just report them. Use `expectNoViolations` for the common case.
 */
export async function a11yCheck(page: Page, options: A11yCheckOptions = {}): Promise<AxeResults> {
    const { rules, include, exclude = [], disableRules = [] } = options;
    let builder = new AxeBuilder({ page });

    // withRules and withTags are mutually exclusive in axe-core: passing a rule
    // list means "only these", so the tag filter must not also be applied.
    builder = rules?.length ? builder.withRules(rules) : builder.withTags(WCAG_AA_TAGS);

    if (include) builder = builder.include(include);
    for (const selector of exclude) builder = builder.exclude(selector);
    if (disableRules.length) builder = builder.disableRules(disableRules);

    return builder.analyze();
}

/** One violation rendered as a readable block, with the offending markup. */
function formatViolation(violation: Result): string {
    const nodes = violation.nodes
        .map((node) => `      ${node.html}\n        ${node.failureSummary?.replace(/\n/g, '\n        ')}`)
        .join('\n');
    return `  [${violation.impact}] ${violation.id}: ${violation.help}\n    ${violation.helpUrl}\n${nodes}`;
}

/**
 * Assert the scan came back clean, printing every violation with its markup
 * and remediation advice. The default Playwright diff on a violations array is
 * unreadable, so this trades it for something you can act on.
 */
export function expectNoViolations(results: AxeResults): void {
    const { violations } = results;
    const summary = violations.length
        ? `${violations.length} accessibility violation(s):\n${violations.map(formatViolation).join('\n\n')}`
        : '';
    expect(summary, summary).toBe('');
}
