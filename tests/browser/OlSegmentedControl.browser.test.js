/**
 * Browser-mode test for <ol-segmented-control>'s stacked label layers. The
 * selected label is a <button> under a clipped <span> twin, so they only read as
 * one label while both shape text identically. The button's UA text reset only
 * exists in a real browser.
 */
import { expect, test } from 'vitest';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OlSegmentedControl.js';

const TEXT_PROPERTIES = ['font-variant-numeric', 'font-style', 'font-stretch', 'font-feature-settings', 'letter-spacing', 'word-spacing', 'text-transform'];

test('the button and ghost layers inherit the same text styles from the page', async () => {
    render(html`
        <div style="font-variant-numeric: tabular-nums; letter-spacing: 0.5px; word-spacing: 2px; text-transform: uppercase">
            <ol-segmented-control value="12">
                <ol-segment value="12">12 months</ol-segment>
                <ol-segment value="28">28 days</ol-segment>
            </ol-segmented-control>
        </div>
    `);

    const el = document.querySelector('ol-segmented-control');
    await el.updateComplete;

    const button = getComputedStyle(el.shadowRoot.querySelector('.layer--base .segment'));
    const ghost = getComputedStyle(el.shadowRoot.querySelector('.layer--active .segment'));

    expect(button.fontVariantNumeric).toBe('tabular-nums');
    for (const property of TEXT_PROPERTIES) {
        expect(button.getPropertyValue(property), property).toBe(ghost.getPropertyValue(property));
    }
});
