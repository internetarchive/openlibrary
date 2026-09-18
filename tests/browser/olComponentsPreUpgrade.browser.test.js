/**
 * Browser-mode tests for the :not(:defined) guards in ol-components.css — jsdom
 * resolves neither :defined nor computed styles from an imported stylesheet.
 * The dialog guard is the load-bearing one: without it an [autofocus] field in
 * the un-upgraded body scrolls the page to a dialog about to be hidden.
 */
import { expect, test } from 'vitest';
import '../../static/css/ol-components.css';

/** Markup for a server-rendered dialog, placed while <ol-dialog> is undefined. */
function insertDialog() {
    const host = document.createElement('div');
    host.innerHTML = `<ol-dialog label="Notes">
        <form><textarea autofocus rows="6"></textarea></form>
        <div slot="footer"><ol-button>Save</ol-button></div>
    </ol-dialog>`;
    document.body.append(host);
    return host.querySelector('ol-dialog');
}

test('an un-upgraded ol-dialog is hidden, so its slotted autofocus field is not focusable', async() => {
    expect(customElements.get('ol-dialog'), 'test must run before OlDialog.js is imported').toBeUndefined();

    const dialog = insertDialog();
    expect(getComputedStyle(dialog).display).toBe('none');

    // display:none removes it as an autofocus candidate: focus() is a no-op.
    const textarea = dialog.querySelector('textarea');
    textarea.focus();
    expect(document.activeElement).not.toBe(textarea);
    expect(textarea.checkVisibility({ visibilityProperty: true })).toBe(false);

    await import('../../openlibrary/components/lit/OlDialog.js');
    await customElements.whenDefined('ol-dialog');
    await dialog.updateComplete;

    // Once defined the guard stops applying; the component owns visibility.
    expect(getComputedStyle(dialog).display).not.toBe('none');
});
