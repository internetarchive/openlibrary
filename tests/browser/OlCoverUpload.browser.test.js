/**
 * Browser-mode tests for <ol-cover-upload>. These exercise the things jsdom
 * can only fake: a real file input + picker, the resulting layout and preview,
 * the button interaction on a real <ol-button> shadow control, and closing the
 * enclosing <ol-dialog>. The network is the only thing stubbed.
 */
import { afterEach, expect, test, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OlCoverUpload.js';
import '../../openlibrary/components/lit/OlDialog.js';

const SAVED = '<div class="imageSaved" data-image-id="7"><div class="saved">Saved!</div></div>';

/** The document's cover art, in the shape `covers/book_cover.html` renders. */
function seedCover() {
    document.body.insertAdjacentHTML(
        'afterbegin',
        `<div class="coverMagic">
            <div class="SRPCover bookCover" style="display: none">
                <a href="#"><img class="cover" src="/old-M.jpg" alt=""></a>
            </div>
            <div class="SRPCoverBlank" style="display: block"></div>
        </div>`,
    );
}

afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
});

test('choosing a real file previews it, and uploading refreshes the page cover', async() => {
    await page.viewport(1000, 900);
    seedCover();
    window.fetch = vi.fn(async() => ({ ok: true, text: async() => SAVED }));

    render(html`
        <ol-cover-upload
            action="/books/OL1M/add-cover"
            doc-type="/type/edition"
            coverstore-url="https://covers.openlibrary.org"
        ></ol-cover-upload>
    `);
    const el = document.querySelector('ol-cover-upload');
    await el.updateComplete;

    const input = el.renderRoot.querySelector('input[type="file"]');
    await userEvent.upload(input, new File(['x'], 'cover.png', { type: 'image/png' }));
    await el.updateComplete;
    expect(el.renderRoot.querySelector('.preview')).not.toBeNull();

    await userEvent.click(el.renderRoot.querySelector('.upload-button'));
    await vi.waitFor(() => expect(el._savedId).toBe(7));

    expect(window.fetch).toHaveBeenCalledTimes(1);
    expect(document.querySelector('.bookCover img').getAttribute('src')).toBe(
        'https://covers.openlibrary.org/b/id/7-M.jpg',
    );
    expect(document.querySelector('.SRPCover').style.display).toBe('block');
    expect(document.querySelector('.SRPCoverBlank').style.display).toBe('none');
});

test('inside ol-dialog, uploading then Finished closes the dialog', async() => {
    await page.viewport(1000, 900);
    window.fetch = vi.fn(async() => ({ ok: true, text: async() => '<div data-image-id="3"></div>' }));

    render(html`
        <ol-dialog label="Book Covers" width="large" style="--ol-dialog-animation-duration: 0ms">
            <ol-cover-upload
                action="/works/OL1W/add-cover"
                doc-type="/type/work"
                coverstore-url="https://c.example"
            ></ol-cover-upload>
        </ol-dialog>
    `);
    const dialog = document.querySelector('ol-dialog');
    dialog.open = true;
    await dialog.updateComplete;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

    const el = document.querySelector('ol-cover-upload');
    await el.updateComplete;
    const input = el.renderRoot.querySelector('input[type="file"]');
    await userEvent.upload(input, new File(['x'], 'c.png', { type: 'image/png' }));
    await userEvent.click(el.renderRoot.querySelector('.upload-button'));
    await vi.waitFor(() => expect(el._savedId).toBe(3));

    await userEvent.click(el.renderRoot.querySelector('.finished'));
    await vi.waitFor(() => expect(dialog.open).toBe(false));
});

test('dragging a file onto the dropzone selects it and highlights the zone', async() => {
    await page.viewport(1000, 900);
    window.fetch = vi.fn(async() => ({ ok: true, text: async() => SAVED }));

    render(html`
        <ol-cover-upload
            action="/books/OL1M/add-cover"
            doc-type="/type/edition"
            coverstore-url="https://covers.openlibrary.org"
        ></ol-cover-upload>
    `);
    const el = document.querySelector('ol-cover-upload');
    await el.updateComplete;

    const zone = el.renderRoot.querySelector('.dropzone');
    const transfer = new DataTransfer();
    transfer.items.add(new File(['x'], 'drag.png', { type: 'image/png' }));

    zone.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    await el.updateComplete;
    expect(el.renderRoot.querySelector('.dropzone--active')).not.toBeNull();

    zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    await el.updateComplete;
    expect(el.renderRoot.querySelector('.drop-content .preview-wrap')).not.toBeNull();
    expect(el.renderRoot.querySelector('.dropzone--active')).toBeNull();
});
