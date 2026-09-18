/**
 * Browser-mode tests for <ol-dialog>'s Tab trap. The trap is keydown-driven and
 * focuses its next stop by hand, so only a real browser shows whether that
 * focus() actually landed — jsdom reports a no-op focus as a success.
 */
import { expect, test } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OLButton.js';
import '../../openlibrary/components/lit/OlDialog.js';

/**
 * The notes dialog's shape: a textarea, a sprite icon below it (the `<use>`
 * carries an href but can't take focus), and a footer button.
 */
async function openDialog() {
    render(html`
        <ol-dialog label="Notes" style="--ol-dialog-animation-duration: 0ms">
            <form>
                <textarea></textarea>
                <p>
                    <svg width="16" height="16"><use href="#icon-eye-off"></use></svg>
                    Only you can see this
                </p>
            </form>
            <div slot="footer">
                <ol-button class="save" variant="primary">Save Note</ol-button>
            </div>
        </ol-dialog>
    `);

    const el = document.querySelector('ol-dialog');
    el.open = true;
    await el.updateComplete;
    // Initial focus is set in a rAF.
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

    return {
        el,
        textarea: el.querySelector('textarea'),
        save: el.querySelector('.save'),
        close: el.shadowRoot.querySelector('.close-button'),
    };
}

test('Tab cycles the dialog\'s controls, skipping the icon that can\'t hold focus', async() => {
    await page.viewport(800, 600);
    const { el, textarea, save, close } = await openDialog();

    expect(document.activeElement).toBe(textarea);

    await userEvent.keyboard('{Tab}');
    expect(document.activeElement).toBe(save);

    await userEvent.keyboard('{Tab}');
    expect(el.shadowRoot.activeElement).toBe(close);

    await userEvent.keyboard('{Tab}');
    expect(document.activeElement).toBe(textarea);
});

test('Shift+Tab runs the same cycle backwards', async() => {
    await page.viewport(800, 600);
    const { el, textarea, save, close } = await openDialog();

    expect(document.activeElement).toBe(textarea);

    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(el.shadowRoot.activeElement).toBe(close);

    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(document.activeElement).toBe(save);

    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(document.activeElement).toBe(textarea);
});
