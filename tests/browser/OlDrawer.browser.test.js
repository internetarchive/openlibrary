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
        <ol-drawer
            label="Menu"
            style="--ol-drawer-enter-duration: 0ms; --ol-drawer-exit-duration: 0ms"
        >
            <nav>
                ${Array.from({ length: ITEMS }, (_, i) => html`
                    <a
                        href="#item-${i}"
                        style="display: block; height: ${ROW_HEIGHT}px;
                               line-height: ${ROW_HEIGHT}px; padding: 0 12px;
                               box-sizing: border-box;"
                    >Item ${i}</a>
                `)}
            </nav>
        </ol-drawer>
    `);

    const el = document.querySelector('ol-drawer');
    el.open = true;
    await el.updateComplete;

    return {
        el,
        /** The panel is the drawer's own scroll container. */
        panel: el.shadowRoot.querySelector('.panel'),
    };
}

test('Tab past the fold scrolls the panel to the newly focused control', async() => {
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

test('Escape closes the drawer through the native dialog cancel event', async() => {
    // jsdom implements neither <dialog>.showModal() nor its cancel event, so
    // this path — the standard way every keyboard user dismisses a drawer —
    // had no coverage anywhere.
    await page.viewport(400, 300);
    const { el } = await openDrawer();

    const reasons = [];
    el.addEventListener('ol-drawer-hide', (event) => reasons.push(event.detail.reason));

    await userEvent.keyboard('{Escape}');
    await el.updateComplete;

    expect(reasons).toEqual(['escape']);
    expect(el.open).toBe(false);
    expect(el.dialog.open).toBe(false);
});
