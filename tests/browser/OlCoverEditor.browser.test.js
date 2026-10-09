/**
 * Browser-mode tests for <ol-cover-editor>: the real file input + picker, a
 * real drag-and-drop, and dragging an image card to reorder (which needs real
 * geometry). The network is the only thing stubbed.
 */
import { afterEach, expect, test, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OlCoverEditor.js';
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

test('choosing a real file previews it, and uploading adds it and refreshes the cover', async() => {
    await page.viewport(1000, 900);
    seedCover();
    window.fetch = vi.fn(async() => ({ ok: true, text: async() => SAVED }));

    render(html`
        <ol-cover-editor
            action="/books/OL1M/add-cover"
            manage-url="/books/OL1M/manage-covers"
            doc-type="/type/edition"
            coverstore-url="https://covers.openlibrary.org"
        ></ol-cover-editor>
    `);
    const el = document.querySelector('ol-cover-editor');
    await el.updateComplete;

    const input = el.renderRoot.querySelector('input[type="file"]');
    await userEvent.upload(input, new File(['x'], 'cover.png', { type: 'image/png' }));
    await el.updateComplete;
    expect(el.renderRoot.querySelector('.preview')).not.toBeNull();

    await userEvent.click(el.renderRoot.querySelector('.upload-button'));
    await vi.waitFor(() => expect(el._images.length).toBe(1));

    expect(window.fetch).toHaveBeenCalledTimes(1);
    expect(el.renderRoot.querySelector('.image--primary')).not.toBeNull();
    expect(document.querySelector('.bookCover img').getAttribute('src')).toBe(
        'https://covers.openlibrary.org/b/id/7-M.jpg',
    );
});

test('dragging a file onto the dropzone selects it and highlights the zone', async() => {
    await page.viewport(1000, 900);
    window.fetch = vi.fn(async() => ({ ok: true, text: async() => SAVED }));

    render(html`
        <ol-cover-editor
            action="/books/OL1M/add-cover"
            doc-type="/type/edition"
            coverstore-url="https://covers.openlibrary.org"
        ></ol-cover-editor>
    `);
    const el = document.querySelector('ol-cover-editor');
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

test('dragging an image card onto another reorders and saves', async() => {
    await page.viewport(1000, 900);
    seedCover();
    window.fetch = vi.fn(async() => ({ ok: true, text: async() => '' }));

    render(html`
        <ol-cover-editor
            action="/books/OL1M/add-cover"
            manage-url="/books/OL1M/manage-covers"
            doc-type="/type/edition"
            coverstore-url="https://covers.openlibrary.org"
            .images=${[
        { id: 1, url: 'https://covers.openlibrary.org/b/id/1-M.jpg' },
        { id: 2, url: 'https://covers.openlibrary.org/b/id/2-M.jpg' },
        { id: 3, url: 'https://covers.openlibrary.org/b/id/3-M.jpg' },
    ]}
        ></ol-cover-editor>
    `);
    const el = document.querySelector('ol-cover-editor');
    await el.updateComplete;
    await el.updateComplete;

    const cards = el.renderRoot.querySelectorAll('.image');
    expect(cards.length).toBe(3);

    const transfer = new DataTransfer();
    cards[0].dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    cards[2].dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    cards[2].dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    await vi.waitFor(() => expect(el._images.map((i) => i.id)).toEqual([2, 3, 1]));

    // dragend commits the live reorder.
    el.renderRoot
        .querySelector('.images-row')
        .dispatchEvent(new DragEvent('dragend', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    await vi.waitFor(() => expect(window.fetch).toHaveBeenCalledTimes(1));

    const body = window.fetch.mock.calls[0][1].body;
    expect(body).toBeInstanceOf(URLSearchParams);
    expect(body.getAll('image')).toEqual(['2', '3', '1', '-1', '-']);
});
