/**
 * Browser-mode tests for <ol-drawer>.
 *
 * The jsdom suite (tests/unit/js/OlDrawer.test.js) documents the limit it
 * works under: "jsdom has no layout engine, so these assert the call rather
 * than the resulting scrollTop, which is verified in the browser." Nothing in
 * tests/e2e actually opens the drawer, so the resulting scrollTop was never
 * verified anywhere. These tests do it: real layout, real focus, real
 * <dialog> behaviour, no DOM stubs of any kind.
 */
import { expect, test } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OlDrawer.js';

const ITEMS = 40;
const ROW_HEIGHT = 40;

/** Mount a drawer whose links overflow the panel, and open it. */
async function openDrawer() {
    render(html`
        <ol-drawer label="Menu" style="--ol-drawer-enter-duration: 0ms; --ol-drawer-exit-duration: 0ms">
            <nav>
                ${Array.from(
                    { length: ITEMS },
                    (_, i) => html`
                        <a
                            href="#item-${i}"
                            style="display: block; height: ${ROW_HEIGHT}px;
                               line-height: ${ROW_HEIGHT}px; padding: 0 12px;
                               box-sizing: border-box;"
                            >Item ${i}</a
                        >
                    `
                )}
            </nav>
        </ol-drawer>
    `);

    const el = document.querySelector('ol-drawer');
    el.open = true;
    await el.updateComplete;

    return {
        el,
        /** The panel is the drawer's own scroll container. */
        panel: el.shadowRoot.querySelector('.panel')
    };
}

test('Tab past the fold scrolls the panel to the newly focused control', async () => {
    // 40 links at 40px each in a 300px-tall panel: everything past the 7th
    // row starts below the fold.
    await page.viewport(400, 300);
    const { panel } = await openDrawer();

    // showModal() landed initial focus on the first stop.
    expect(document.activeElement.textContent).toBe('Item 0');

    // Twenty Tabs later focus sits on a control that began off-screen.
    for (let i = 0; i < 20; i++) {
        await userEvent.keyboard('{Tab}');
    }
    expect(document.activeElement.textContent).toBe('Item 20');

    // The panel scrolled itself to bring the stop into view — the thing the
    // jsdom suite can only assert was *requested*.
    expect(panel.scrollTop).toBeGreaterThan(0);

    // And the control really is inside the panel's visible box now, which is
    // the WCAG 2.4.11 guarantee the Tab trap exists to keep.
    const focused = document.activeElement.getBoundingClientRect();
    const box = panel.getBoundingClientRect();
    expect(focused.top).toBeGreaterThanOrEqual(box.top - 1);
    expect(focused.bottom).toBeLessThanOrEqual(box.bottom + 1);
});

test('Escape closes the drawer through the native dialog cancel event', async () => {
    // jsdom implements neither <dialog>.showModal() nor its cancel event, so
    // this path — the standard way every keyboard user dismisses a drawer —
    // had no coverage anywhere.
    await page.viewport(400, 300);
    const { el } = await openDrawer();

    const reasons = [];
    el.addEventListener('ol-drawer-hide', event => reasons.push(event.detail.reason));

    await userEvent.keyboard('{Escape}');
    await el.updateComplete;

    expect(reasons).toEqual(['escape']);
    expect(el.open).toBe(false);
    expect(el.dialog.open).toBe(false);
});

/** Mount a modeless drawer beside a page button, and open it. */
async function openModelessDrawer() {
    render(html`
        <button id="page-button" style="position: fixed; top: 20px; left: 20px">On the page</button>
        <ol-drawer modeless label="Add a detail" style="--ol-drawer-enter-duration: 0ms; --ol-drawer-exit-duration: 0ms">
            <input id="answer" aria-label="Answer" />
        </ol-drawer>
    `);
    const el = document.querySelector('ol-drawer');
    el.open = true;
    await el.updateComplete;
    return { el, panel: el.shadowRoot.querySelector('.panel') };
}

test('a modeless drawer leaves the page beside it in use', async () => {
    await page.viewport(1000, 600);
    const { el, panel } = await openModelessDrawer();

    // Not modal: no scrim, no aria-modal claim, no scroll lock on the page.
    expect(el.shadowRoot.querySelector('.scrim')).toBeNull();
    expect(el.dialog.hasAttribute('aria-modal')).toBe(false);
    expect(el.dialog.matches(':modal')).toBe(false);
    expect(getComputedStyle(document.body).overflow).not.toBe('hidden');

    // A side panel on the end edge, full height.
    const box = panel.getBoundingClientRect();
    expect(box.right).toBeCloseTo(1000, 0);
    expect(box.height).toBeCloseTo(600, 0);

    // The viewport-filling dialog must not swallow clicks meant for the page.
    let clicks = 0;
    const button = document.getElementById('page-button');
    button.addEventListener('click', () => clicks++);
    await userEvent.click(button);
    expect(clicks).toBe(1);
    expect(el.open).toBe(true);
});

test('Escape closes a modeless drawer from inside it, not from the page', async () => {
    await page.viewport(1000, 600);
    const { el } = await openModelessDrawer();
    const reasons = [];
    el.addEventListener('ol-drawer-hide', event => reasons.push(event.detail.reason));

    document.getElementById('page-button').focus();
    await userEvent.keyboard('{Escape}');
    await el.updateComplete;
    expect(el.open).toBe(true);

    document.getElementById('answer').focus();
    await userEvent.keyboard('{Escape}');
    await el.updateComplete;
    expect(reasons).toEqual(['escape']);
    expect(el.open).toBe(false);
    expect(el.dialog.open).toBe(false);
});

test('Tab leaves a modeless drawer instead of cycling inside it', async () => {
    await page.viewport(1000, 600);
    await openModelessDrawer();
    document.getElementById('answer').focus();
    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(document.activeElement.id).toBe('page-button');
});

test('under the tablet breakpoint a modeless drawer is a bottom sheet', async () => {
    await page.viewport(390, 700);
    const { panel } = await openModelessDrawer();
    const box = panel.getBoundingClientRect();
    expect(box.left).toBeCloseTo(0, 0);
    expect(box.width).toBeCloseTo(390, 0);
    expect(box.bottom).toBeCloseTo(700, 0);
    // Leaves the top of the page in view.
    expect(box.top).toBeGreaterThan(700 * 0.1);
});
