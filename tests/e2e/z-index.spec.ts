import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

/**
 * Guards for the z-index token system (static/css/tokens/z-index.css).
 *
 * These catch two failures that reviewing a diff does not:
 *
 * 1. A token that fails to resolve. `z-index: var(--typo)` is invalid at
 *    computed-value time, so the declaration is dropped entirely and the
 *    element falls back to `auto` — not to whatever number it used to have.
 *    Nothing looks wrong until two things happen to overlap.
 * 2. An ordering that survives only by document order. Siblings with equal
 *    z-index paint in tree order, so a template reshuffle can invert a
 *    deliberate pair without touching a line of CSS.
 *
 * /developers/design renders every Lit component on one page, so it is the
 * cheapest surface for both.
 */

const DESIGN_PAGE = '/developers/design';

/** Custom elements whose shadow roots these tests read. */
const COMPONENTS = ['ol-tooltip', 'ol-popover', 'ol-carousel', 'ol-segmented-control'];

/** The popover in the design page's own section, not one nested in a sibling component. */
const POPOVER = '#popover ol-popover';

declare global {
    interface Window {
        /**
         * Deepest element painted at a viewport point, piercing open shadow
         * roots, plus whether `.panel` is one of its flat-tree ancestors.
         * document.elementFromPoint retargets to the host and slotted content
         * is not in the shadow tree, so neither a plain hit test nor
         * `.contains()` answers this on its own.
         */
        __olHitTest: (x: number, y: number) => { inPanel: boolean; hit: string };
    }
}

function installHitTest(page: Page) {
    return page.addInitScript(() => {
        window.__olHitTest = (x, y) => {
            let el: Element | null = document.elementFromPoint(x, y);
            while (el?.shadowRoot) {
                const inner = el.shadowRoot.elementFromPoint(x, y);
                if (!inner || inner === el) break;
                el = inner;
            }
            const hit = el;

            let node: Node | null = el;
            let inPanel = false;
            while (node) {
                if (node instanceof Element && node.classList.contains('panel')) {
                    inPanel = true;
                    break;
                }
                const slot = node instanceof Element ? node.assignedSlot : null;
                node = slot ?? (node.parentNode instanceof ShadowRoot ? node.parentNode.host : node.parentNode);
            }

            return {
                inPanel,
                hit: hit ? `${hit.tagName.toLowerCase()}.${hit.className || '(no class)'}` : 'none',
            };
        };
    });
}

async function gotoDesignPage(page: Page) {
    await page.goto(DESIGN_PAGE);
    await page.evaluate(
        names => Promise.all(names.map(n => customElements.whenDefined(n))),
        COMPONENTS,
    );
}

/** Computed z-index of `inner` inside the first `host`'s shadow root. */
async function shadowZIndex(page: Page, host: string, inner: string): Promise<string> {
    // Lit renders asynchronously, so the shadow root may not be populated yet.
    await page.waitForFunction(
        ([h, i]) => !!document.querySelector(h)?.shadowRoot?.querySelector(i),
        [host, inner],
    );
    return page.evaluate(([h, i]) => {
        const el = document.querySelector(h)!.shadowRoot!.querySelector(i)!;
        return getComputedStyle(el).zIndex;
    }, [host, inner]);
}

test.describe('z-index tokens', () => {
    test('semantic tokens resolve on the document root', async ({ page }) => {
        await page.goto(DESIGN_PAGE);
        const tokens = await page.evaluate(() => {
            const styles = getComputedStyle(document.documentElement);
            const read = (name: string) => styles.getPropertyValue(name).trim();
            return {
                behind: read('--z-index-behind'),
                base: read('--z-index-base'),
                raised: read('--z-index-raised'),
                sticky: read('--z-index-sticky'),
                fixed: read('--z-index-fixed'),
                dropdown: read('--z-index-dropdown'),
                modal: read('--z-index-modal'),
                overlay: read('--z-index-overlay'),
                toast: read('--z-index-toast'),
                local1: read('--z-index-local-1'),
                local2: read('--z-index-local-2'),
                local3: read('--z-index-local-3'),
                local4: read('--z-index-local-4'),
                local5: read('--z-index-local-5'),
            };
        });
        // An empty string for any of these means tokens.css did not load, which
        // silently turns every tokenised z-index on the page into `auto`.
        expect(tokens).toEqual({
            behind: '-1',
            base: '1',
            raised: '2',
            sticky: '3',
            fixed: '10',
            dropdown: '999',
            modal: '9999',
            overlay: '99999',
            toast: '999999',
            local1: '1',
            local2: '2',
            local3: '3',
            local4: '4',
            local5: '5',
        });
    });

    test('component z-index declarations resolve to numbers', async ({ page }) => {
        await gotoDesignPage(page);

        const cases: [string, string, string][] = [
            ['ol-tooltip', '.tooltip', '999'],
            // The carousel's arrows must outrank its edge gradients. Both are
            // pointer-events: none, so paint order is the only observable —
            // hit-testing cannot check this pair.
            ['ol-carousel', '.edge-fade', '1'],
            ['ol-carousel', '.arrow', '2'],
            ['ol-segmented-control', '.pill', '1'],
            ['ol-segmented-control', '.layer--base', '2'],
            ['ol-segmented-control', '.layer--active', '3'],
        ];

        for (const [host, inner, expected] of cases) {
            // `auto` here means the token failed to resolve.
            expect(await shadowZIndex(page, host, inner), `${host} ${inner}`).toBe(expected);
        }
    });
});

/**
 * Open the design page's popover and wait out its entry animation.
 * The trigger is slotted light DOM; the click handler lives on the slot.
 */
async function openPopover(page: Page) {
    await page.locator(POPOVER).first().locator('[slot="trigger"]').click();
    await page.waitForFunction(
        sel => document.querySelector(sel)?.shadowRoot
            ?.querySelector('.panel')?.getAttribute('data-state') === 'open',
        POPOVER,
    );
}

test.describe('popover tray stacking @mobile', () => {
    // .panel and .backdrop both sit at --z-index-dropdown. The panel wins only
    // because render() emits it after the backdrop. These assert the outcome
    // rather than the number, so reordering the template fails here.

    test.beforeEach(async ({ page }) => {
        await installHitTest(page);
        await gotoDesignPage(page);
        await openPopover(page);
    });

    test('tray renders above its own scrim', async ({ page }) => {
        expect(await shadowZIndex(page, POPOVER, '.panel')).toBe('999');
        expect(await shadowZIndex(page, POPOVER, '.backdrop')).toBe('999');

        const result = await page.evaluate(sel => {
            const panel = document.querySelector(sel)!.shadowRoot!.querySelector('.panel')!;
            const box = panel.getBoundingClientRect();
            return window.__olHitTest(box.x + box.width / 2, box.y + box.height / 2);
        }, POPOVER);

        expect(result.inPanel, `expected the panel, hit ${result.hit}`).toBe(true);
    });

    test('scrim covers the page above the tray', async ({ page }) => {
        // Halfway between the viewport top and the tray: the scrim must own this
        // point. If it fell behind the page, a page element answers instead.
        const hit = await page.evaluate(sel => {
            const panel = document.querySelector(sel)!.shadowRoot!.querySelector('.panel')!;
            const top = panel.getBoundingClientRect().top;
            return window.__olHitTest(window.innerWidth / 2, Math.max(10, top / 2)).hit;
        }, POPOVER);

        expect(hit).toContain('backdrop');
    });
});
