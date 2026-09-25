/**
 * The search modal renders an [autofocus] input inside an <ol-dialog> in its
 * own shadow root, where the page-level `ol-dialog:not(:defined)` guard in
 * ol-components.css does not apply. The modal mounts from the main bundle,
 * which can run before the components bundle defines ol-dialog; without a
 * shadow-scoped guard the browser focuses the input at first paint and
 * scrolls the page to the (closed) modal at the bottom of the body.
 */
import { expect, test } from 'vitest';
import '../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';

test('the un-upgraded ol-dialog inside the search modal is hidden, so its autofocus input is not focusable', async() => {
    expect(customElements.get('ol-dialog'), 'test must run before OlDialog.js is imported').toBeUndefined();

    const modal = document.createElement('ol-search-modal');
    document.body.append(modal);
    await modal.updateComplete;

    const dialog = modal.shadowRoot.querySelector('ol-dialog');
    expect(getComputedStyle(dialog).display).toBe('none');

    const input = modal.shadowRoot.querySelector('.search-input');
    expect(input.hasAttribute('autofocus')).toBe(true);
    input.focus();
    expect(modal.shadowRoot.activeElement).toBeNull();
    expect(window.scrollY).toBe(0);

    await import('../../openlibrary/components/lit/OlDialog.js');
    await customElements.whenDefined('ol-dialog');
    await dialog.updateComplete;

    // Once defined the guard stops applying; the component owns visibility.
    expect(getComputedStyle(dialog).display).not.toBe('none');
});
