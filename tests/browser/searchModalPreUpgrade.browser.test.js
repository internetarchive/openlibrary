/**
 * The search modal renders an [autofocus] input inside an <ol-dialog> in its own
 * shadow root. The main bundle can run before ol-components.js defines ol-dialog,
 * and an un-upgraded dialog would let that input take focus at first paint and
 * scroll the page, so initSearchModal waits for the definition before mounting.
 */
import { expect, test } from 'vitest';
import { initSearchModal } from '../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';

test('initSearchModal waits for ol-dialog to be defined before mounting the modal', async() => {
    expect(customElements.get('ol-dialog'), 'test must run before OlDialog.js is imported').toBeUndefined();

    const trigger = document.createElement('button');
    trigger.type = 'button';
    document.body.append(trigger);

    const modal = initSearchModal(trigger);
    expect(initSearchModal(trigger), 'a second call is a no-op').toBeNull();
    await new Promise(requestAnimationFrame);
    expect(modal.isConnected).toBe(false);

    await import('../../openlibrary/components/lit/OlDialog.js');
    await customElements.whenDefined('ol-dialog');
    await modal.updateComplete;

    expect(modal.isConnected).toBe(true);
    const input = modal.shadowRoot.querySelector('.search-input');
    expect(input.hasAttribute('autofocus')).toBe(true);
    expect(modal.shadowRoot.activeElement).toBeNull();

    // The trigger is wired once mounted: a click opens the dialog and focuses the input.
    trigger.click();
    expect(modal.open).toBe(true);
    expect(modal.shadowRoot.activeElement).toBe(input);
});
