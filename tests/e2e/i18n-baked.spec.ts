import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'fs';

/**
 * Do pages render the translations baked into the olbase image, or the .po files
 * committed in the checkout? Driven by tests/e2e/i18n-baked/run.sh; skipped otherwise.
 *
 *   I18N_E2E_DISCOVER=<out.json>  render I18N_E2E_PAGES in English and save each page's
 *                                 visible text (input to make_fixture.py select)
 *   I18N_E2E_FIXTURE=<fixture.json> I18N_E2E_EXPECT=baked|committed
 *                                 assert each fixture string renders as that path should
 */

const DISCOVER = process.env.I18N_E2E_DISCOVER;
const FIXTURE = process.env.I18N_E2E_FIXTURE;
const EXPECT = process.env.I18N_E2E_EXPECT;
// Not "/": the stack runs no Solr, so the homepage's subject counts are None and
// home/categories.html's ungettext() raises for every language with a Plural-Forms header.
const PAGES = (process.env.I18N_E2E_PAGES || '/search?q=e2e,/search/inside?q=e2e,/account/login,/account/create,/search/authors?q=e2e,/subjects,/lists').split(
    ','
);

type Item = { msgid: string; msgstr: string; page: string };
type Fixture = Record<string, Record<string, Item[]>>;

async function visibleText(page: Page, url: string): Promise<string> {
    const response = await page.goto(url);
    expect(response?.status(), url).toBeLessThan(400);
    return page.evaluate(() => document.body.innerText);
}

function withLang(url: string, lang: string): string {
    return `${url}${url.includes('?') ? '&' : '?'}lang=${lang}`;
}

test.describe('baked translations @i18n-baked', () => {
    test.skip(!DISCOVER && !FIXTURE, 'run via tests/e2e/i18n-baked/run.sh');

    if (DISCOVER) {
        test('discover English page text', async ({ page }) => {
            // The page list is a starting set: skip pages web.py does not serve rather
            // than fail, and require at least one usable page.
            const out: Record<string, string> = {};
            for (const url of PAGES) {
                const response = await page.goto(withLang(url, 'en'));
                const status = response?.status() ?? 0;
                if (status >= 400) {
                    console.log(`discover: skipping ${url} (HTTP ${status})`);
                    continue;
                }
                out[url] = await page.evaluate(() => document.body.innerText);
            }
            expect(Object.keys(out).length).toBeGreaterThan(0);
            writeFileSync(DISCOVER, JSON.stringify(out, null, 2));
        });
    }

    if (FIXTURE) {
        if (EXPECT !== 'baked' && EXPECT !== 'committed') {
            throw new Error('I18N_E2E_EXPECT must be "baked" or "committed"');
        }
        const fixture: Fixture = JSON.parse(readFileSync(FIXTURE, 'utf-8'));
        for (const [lang, classes] of Object.entries(fixture)) {
            for (const [cls, items] of Object.entries(classes)) {
                for (const item of items) {
                    test(`${EXPECT} ${lang} ${cls}: ${item.msgid}`, async ({ page }) => {
                        const text = await visibleText(page, withLang(item.page, lang));
                        if (EXPECT === 'committed' && cls === 'english_before') {
                            // Not translated in the committed .po: the dev path shows English.
                            expect(text).toContain(item.msgid);
                            expect(text).not.toContain(item.msgstr);
                        } else {
                            // baked: every class shows the translation. committed: "both" is
                            // translated identically in the committed file (proves the dev
                            // path's translations are loaded at all).
                            expect(text).toContain(item.msgstr);
                        }
                    });
                }
            }
        }
    }
});
