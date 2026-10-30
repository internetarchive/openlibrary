/**
 * Browser-mode tests for <ol-lightbox>.
 *
 * Everything the component does is a browser primitive jsdom can only stub:
 * `<dialog>.showModal()`, real layout for the FLIP rects, rAF-driven springs,
 * and pointer capture for the drag. The spring and rect maths are unit-tested
 * in tests/unit/js; these cover the lifecycle around them.
 */
import { expect, test } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OlLightbox.js';

// A 2:3 cover, drawn rather than fetched so the suite needs no network.
const THUMB_SRC = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="180"><rect width="120" height="180" fill="#7a5c3e"/></svg>')}`;
const FULL_SRC = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600"><rect width="400" height="600" fill="#3e5c7a"/></svg>')}`;

async function mount() {
    await page.viewport(1280, 800);
    render(html`
        <div style="padding: 100px">
            <ol-lightbox src=${FULL_SRC} alt="Cover of The Secret Garden" label-close="Close">
                <a href=${FULL_SRC} style="display: block; width: 120px">
                    <img src=${THUMB_SRC} alt="Cover of The Secret Garden" style="display: block; width: 120px; height: 180px" />
                </a>
            </ol-lightbox>
        </div>
    `);
    const el = document.querySelector('ol-lightbox');
    await el.updateComplete;
    // The thumbnail needs its natural size before the morph can measure it.
    const thumb = el.querySelector('img');
    if (!thumb.complete) await new Promise(resolve => thumb.addEventListener('load', resolve, { once: true }));
    return {
        el,
        thumb,
        dialog: el.shadowRoot.querySelector('dialog'),
        image: el.shadowRoot.querySelector('.image'),
        scrim: el.shadowRoot.querySelector('.scrim'),
        closeButton: el.shadowRoot.querySelector('.close-button')
    };
}

/** Waits for the open or close morph to land. */
const afterEvent = (el, name) => new Promise(resolve => el.addEventListener(name, resolve, { once: true }));

/** `ol-lightbox-after-show` fires while the spring is still overshooting; this waits for it to rest. */
const settled = image => expect.poll(() => image.style.transform, { timeout: 3000 }).toBe('translate(0px, 0px) scale(1)');

/** The translate() of an inline transform, as numbers. */
function translateOf(image) {
    const [, x, y] = image.style.transform.match(/translate\(([-\d.]+)px, ([-\d.]+)px\)/) || [];
    return { x: parseFloat(x), y: parseFloat(y) };
}

test('clicking the thumbnail opens a modal dialog with the image laid out in the viewport', async () => {
    const { el, thumb, dialog, image, scrim } = await mount();
    const landed = afterEvent(el, 'ol-lightbox-after-show');

    await userEvent.click(thumb);
    await landed;
    await settled(image);

    expect(el.open).toBe(true);
    expect(dialog.open).toBe(true);
    expect(dialog.matches(':modal')).toBe(true);
    expect(scrim.style.opacity).toBe('1');
    // The link was not followed.
    expect(location.href).not.toContain('data:image');

    // Centred, padded, and no taller than the viewport.
    const rect = image.getBoundingClientRect();
    expect(rect.height).toBeLessThanOrEqual(800);
    expect(Math.abs(rect.x + rect.width / 2 - 640)).toBeLessThan(1);
    expect(Math.abs(rect.y + rect.height / 2 - 400)).toBeLessThan(1);
    // Upscaled from 400×600 by the default cap of 2 would be 800×1200; the
    // viewport height binds first.
    expect(rect.width / rect.height).toBeCloseTo(2 / 3, 2);
});

test('the thumbnail is hidden while open and shown again on close', async () => {
    const { el, thumb } = await mount();
    const landed = afterEvent(el, 'ol-lightbox-after-show');
    await userEvent.click(thumb);
    await landed;
    expect(thumb.style.visibility).toBe('hidden');

    const hidden = afterEvent(el, 'ol-lightbox-after-hide');
    el.open = false;
    await hidden;
    expect(thumb.style.visibility).toBe('');
});

test('Escape closes through the native cancel event, with the reason, and restores focus', async () => {
    const { el, thumb, dialog } = await mount();
    const link = el.querySelector('a');
    link.focus();
    const landed = afterEvent(el, 'ol-lightbox-after-show');
    await userEvent.click(thumb);
    await landed;

    const reasons = [];
    el.addEventListener('ol-lightbox-hide', e => reasons.push(e.detail.reason));
    const hidden = afterEvent(el, 'ol-lightbox-after-hide');
    await userEvent.keyboard('{Escape}');
    await hidden;

    expect(dialog.open).toBe(false);
    expect(reasons).toEqual(['escape']);
    await expect.poll(() => document.activeElement).toBe(link);
});

test('a click on the scrim, the image, or the close button closes with its own reason', async () => {
    const { el, thumb, image, scrim, closeButton } = await mount();
    const reasons = [];
    el.addEventListener('ol-lightbox-hide', e => reasons.push(e.detail.reason));

    // The scrim is clicked in its bottom-left corner: its centre is under the
    // image and its top-right under the close button.
    const scrimCorner = () => ({ position: { x: 10, y: scrim.getBoundingClientRect().height - 10 } });
    for (const [target, reason, options] of [
        [scrim, 'scrim', scrimCorner],
        [image, 'image', () => ({})],
        [closeButton, 'close', () => ({})]
    ]) {
        const landed = afterEvent(el, 'ol-lightbox-after-show');
        await userEvent.click(thumb);
        await landed;
        await settled(image);
        const hidden = afterEvent(el, 'ol-lightbox-after-hide');
        await userEvent.click(target, options());
        await hidden;
        expect(el.open).toBe(false);
        expect(reasons.at(-1)).toBe(reason);
    }
});

test('Tab keeps focus on the close button, the only stop', async () => {
    const { el, thumb, closeButton } = await mount();
    const landed = afterEvent(el, 'ol-lightbox-after-show');
    await userEvent.click(thumb);
    await landed;

    expect(el.shadowRoot.activeElement).toBe(closeButton);
    await userEvent.keyboard('{Tab}');
    expect(el.shadowRoot.activeElement).toBe(closeButton);
    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(el.shadowRoot.activeElement).toBe(closeButton);
});

test('a modifier-click is left to the link', async () => {
    const { el, thumb } = await mount();
    const link = el.querySelector('a');
    let defaultPrevented = null;
    // Catch the click after the component has had its say, and stop the
    // browser from actually opening a tab.
    link.addEventListener('click', e => {
        defaultPrevented = e.defaultPrevented;
        e.preventDefault();
    });
    await userEvent.click(thumb, { modifiers: ['Meta'] });
    expect(defaultPrevented).toBe(false);
    expect(el.open).toBe(false);
});

test('a vertical drag past the lock threshold follows the pointer and a release dismisses', async () => {
    const { el, thumb, image, scrim, dialog } = await mount();
    const landed = afterEvent(el, 'ol-lightbox-after-show');
    await userEvent.click(thumb);
    await landed;
    await settled(image);

    const rect = image.getBoundingClientRect();
    const cx = rect.x + rect.width / 2;
    const cy = rect.y + rect.height / 2;
    const pointer = (type, x, y) =>
        dialog.dispatchEvent(new PointerEvent(type, { bubbles: true, composed: true, pointerId: 1, clientX: x, clientY: y, button: 0, isPrimary: true }));

    image.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true, pointerId: 1, clientX: cx, clientY: cy, button: 0, isPrimary: true }));
    for (let i = 1; i <= 10; i++) pointer('pointermove', cx, cy + i * 30);

    const { x, y } = translateOf(image);
    expect(Math.abs(x)).toBeLessThan(1);
    expect(y).toBeCloseTo(300, 0);
    expect(parseFloat(scrim.style.opacity)).toBeLessThan(1);

    const reasons = [];
    el.addEventListener('ol-lightbox-hide', e => reasons.push(e.detail.reason));
    const hidden = afterEvent(el, 'ol-lightbox-after-hide');
    pointer('pointerup', cx, cy + 300);
    await hidden;
    expect(reasons).toEqual(['swipe']);
    expect(dialog.open).toBe(false);
});

test('a sideways drag is ignored and the image stays put', async () => {
    const { el, thumb, image, dialog } = await mount();
    const landed = afterEvent(el, 'ol-lightbox-after-show');
    await userEvent.click(thumb);
    await landed;

    // Deliberately *not* settled: grabbing the image mid-overshoot cancels
    // that spring, and an abandoned drag has to put it back by itself.
    const rect = image.getBoundingClientRect();
    const cx = rect.x + rect.width / 2;
    const cy = rect.y + rect.height / 2;
    const opts = x => ({ bubbles: true, composed: true, pointerId: 1, clientX: x, clientY: cy, button: 0, isPrimary: true });
    image.dispatchEvent(new PointerEvent('pointerdown', opts(cx)));
    dialog.dispatchEvent(new PointerEvent('pointermove', opts(cx + 60)));
    dialog.dispatchEvent(new PointerEvent('pointerup', opts(cx + 60)));

    await settled(image);
    expect(el.open).toBe(true);
});

test('ol-lightbox-hide can be cancelled to keep it open', async () => {
    const { el, thumb, dialog } = await mount();
    const landed = afterEvent(el, 'ol-lightbox-after-show');
    await userEvent.click(thumb);
    await landed;

    el.addEventListener('ol-lightbox-hide', e => e.preventDefault(), { once: true });
    el.open = false;
    await el.updateComplete;
    expect(el.open).toBe(true);
    expect(dialog.open).toBe(true);
});
