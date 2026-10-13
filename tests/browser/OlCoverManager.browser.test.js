/**
 * Browser-mode tests for <ol-cover-manager> inside its dialog: the real file
 * input, a real file drop, and the page behind the dialog picking up the saved
 * cover (via covers.js). Only the network is stubbed.
 */
import { afterEach, beforeAll, expect, test, vi } from 'vitest';
import { userEvent } from 'vitest/browser';
import '../../openlibrary/components/lit/OLButton.js';
import '../../openlibrary/components/lit/OlDialog.js';
import '../../openlibrary/components/lit/OlCoverManager.js';

const COVERSTORE = 'https://covers.openlibrary.org';

const EDITION_STATE = {
    key: '/books/OL1M',
    current: 'img:10',
    items: [{ id: 'img:10', kind: 'upload', image_id: 10, thumb: '10-M.jpg' }],
};

const UPLOADED = { id: 'img:77', kind: 'upload', image_id: 77, thumb: '77-M.jpg' };

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

let calls;

/** Answer `METHOD url` routes with JSON; anything else is a test bug. */
function stubFetch(routes) {
    calls = [];
    window.fetch = vi.fn(async(url, init = {}) => {
        const route = `${init.method ?? 'GET'} ${url}`;
        calls.push({ route, init });
        if (!(route in routes)) throw new Error(`Unexpected fetch: ${route}`);
        return json(routes[route]);
    });
}

/** The edition page's cover (covers/book_cover.html) plus the change button and dialog (covers/change.html). */
function seedEditionPage() {
    document.body.innerHTML = `
        <div class="coverMagic">
            <div class="SRPCover bookCover" style="display: block">
                <a href="${COVERSTORE}/b/id/10-L.jpg" aria-controls="seeImage" class="coverLook">
                    <img class="cover" src="${COVERSTORE}/b/id/10-M.jpg" srcset="${COVERSTORE}/b/id/10-L.jpg 2x" alt="">
                </a>
            </div>
            <div class="SRPCoverBlank" style="display: none"></div>
        </div>
        <ol-dialog id="seeImage" label="Cover"><img class="cover cover-preview" src="${COVERSTORE}/b/id/10-L.jpg" alt=""></ol-dialog>
        <ol-button class="manageCovers" aria-controls="addImage-0"
            data-config='${JSON.stringify({ key: '/type/edition', url: COVERSTORE, selector: '.bookCover img' })}'>Manage</ol-button>
        <ol-dialog id="addImage-0" label="Manage covers" style="--ol-dialog-animation-duration: 0ms">
            <ol-cover-manager doc-key="/books/OL1M"></ol-cover-manager>
        </ol-dialog>`;
}

/** The author page renders authors/infobox twice (mobile + desktop), each with its own photo, preview dialog, and manager. */
function seedAuthorPage() {
    const infobox = (imagesId) => `
        <div class="infobox">
            <div class="author coverMagic">
                <div class="SRPCover bookCover">
                    <a href="${COVERSTORE}/a/id/5-L.jpg" aria-controls="seeImage-${imagesId}" class="coverLook">
                        <img class="cover" src="${COVERSTORE}/a/id/5-M.jpg" style="aspect-ratio: 0.75" alt="">
                    </a>
                </div>
            </div>
            <ol-dialog id="seeImage-${imagesId}" label="Ada"><img class="cover cover-preview" src="${COVERSTORE}/a/id/5-L.jpg" alt=""></ol-dialog>
            <ol-button class="manageCovers" aria-controls="addImage-${imagesId}"
                data-config='${JSON.stringify({ key: '/type/author', url: COVERSTORE, selector: '.bookCover img' })}'>Manage</ol-button>
            <ol-dialog id="addImage-${imagesId}" label="Manage photos" style="--ol-dialog-animation-duration: 0ms">
                <ol-cover-manager doc-key="/authors/OL1A"></ol-cover-manager>
            </ol-dialog>
        </div>`;
    document.body.innerHTML = infobox('mobile') + infobox('desktop');
}

/** Open the manager's dialog and wait for its listing to load. */
async function openManager(dialogId) {
    const dialog = document.getElementById(dialogId);
    dialog.open = true;
    await dialog.updateComplete;
    const manager = dialog.querySelector('ol-cover-manager');
    await vi.waitFor(() => expect(manager._loadState).toBe('ready'));
    await manager.updateComplete;
    return manager;
}

const q = (el, selector) => el.renderRoot.querySelector(selector);
const saveButton = (el) => q(el, 'ol-button[variant="primary"]');

beforeAll(async() => {
    const { initCoversChange } = await import('../../openlibrary/plugins/openlibrary/js/covers.js');
    // Listens on document, so once for the whole file.
    initCoversChange();
});

afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
});

test('choosing a real file uploads it, and Save puts it on the page at full resolution', async() => {
    seedEditionPage();
    stubFetch({
        'GET /books/OL1M/covers.json': EDITION_STATE,
        'POST /books/OL1M/covers/upload.json': UPLOADED,
        'POST /books/OL1M/covers.json': { cover_id: 77 },
    });
    const manager = await openManager('addImage-0');

    await userEvent.upload(q(manager, 'input[type="file"]'), new File(['x'], 'Ada\'s cover.png', { type: 'image/png' }));
    await vi.waitFor(() => expect(manager._selected).toBe('img:77'));

    // The firewall rejects some real filenames (#13286), so the upload goes out under a neutral one.
    const upload = calls.find((c) => c.route === 'POST /books/OL1M/covers/upload.json');
    expect(upload.init.body.get('file').name).toBe('image.png');

    await manager.updateComplete;
    expect(saveButton(manager).disabled).toBe(false);
    await userEvent.click(saveButton(manager));

    await vi.waitFor(() => expect(document.querySelector('.bookCover img').getAttribute('src')).toBe(`${COVERSTORE}/b/id/77-M.jpg`));
    const save = calls.find((c) => c.route === 'POST /books/OL1M/covers.json');
    expect(JSON.parse(save.init.body)).toEqual({ image_id: 77, added: [77], removed: [] });
    expect(document.querySelector('.bookCover img').getAttribute('srcset')).toBe(`${COVERSTORE}/b/id/77-L.jpg 2x`);
    expect(document.querySelector('#seeImage img').getAttribute('src')).toBe(`${COVERSTORE}/b/id/77-L.jpg`);
    expect(document.querySelector('.coverLook').getAttribute('href')).toBe(`${COVERSTORE}/b/id/77-L.jpg`);
    await vi.waitFor(() => expect(document.getElementById('addImage-0').open).toBe(false));
});

test('dragging a file over the grid shows the drop target, and dropping it uploads', async() => {
    seedEditionPage();
    stubFetch({
        'GET /books/OL1M/covers.json': EDITION_STATE,
        'POST /books/OL1M/covers/upload.json': UPLOADED,
    });
    const manager = await openManager('addImage-0');

    const zone = q(manager, '.grid-wrap');
    const transfer = new DataTransfer();
    transfer.items.add(new File(['x'], 'drop.jpg', { type: 'image/jpeg' }));

    zone.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    zone.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    await manager.updateComplete;
    expect(q(manager, '.drop-target')).not.toBeNull();

    zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    await manager.updateComplete;
    expect(q(manager, '.drop-target')).toBeNull();

    await vi.waitFor(() => expect(manager._selected).toBe('img:77'));
    const upload = calls.find((c) => c.route === 'POST /books/OL1M/covers/upload.json');
    expect(upload.init.body.get('file').name).toBe('image.jpg');
});

test('saving an author photo updates both infobox copies and both preview dialogs', async() => {
    seedAuthorPage();
    const state = {
        key: '/authors/OL1A',
        current: 'img:5',
        items: [
            { id: 'img:5', kind: 'upload', image_id: 5, thumb: '5-M.jpg' },
            { id: 'img:6', kind: 'upload', image_id: 6, thumb: '6-M.jpg' },
        ],
    };
    stubFetch({
        'GET /authors/OL1A/photos.json': state,
        'POST /authors/OL1A/photos.json': { cover_id: 6 },
    });
    // Save from the desktop copy; the mobile copy must follow.
    const manager = await openManager('addImage-desktop');

    await userEvent.click(manager.renderRoot.querySelectorAll('.pick')[1]);
    await manager.updateComplete;
    await userEvent.click(saveButton(manager));

    await vi.waitFor(() => {
        for (const img of document.querySelectorAll('.bookCover img')) {
            expect(img.getAttribute('src')).toBe(`${COVERSTORE}/a/id/6-M.jpg`);
            // The old photo's inline aspect ratio would squeeze the new one.
            expect(img.style.aspectRatio).toBe('');
        }
    });
    for (const imagesId of ['mobile', 'desktop']) {
        expect(document.querySelector(`#seeImage-${imagesId} img`).getAttribute('src')).toBe(`${COVERSTORE}/a/id/6-L.jpg`);
        expect(document.querySelector(`.coverLook[aria-controls="seeImage-${imagesId}"]`).getAttribute('href')).toBe(`${COVERSTORE}/a/id/6-L.jpg`);
    }
});

test('the Paste button uploads an image read from the clipboard', async() => {
    seedEditionPage();
    stubFetch({
        'GET /books/OL1M/covers.json': EDITION_STATE,
        'POST /books/OL1M/covers/upload.json': UPLOADED,
    });
    vi.spyOn(navigator.clipboard, 'read').mockResolvedValue([
        { types: ['text/html', 'image/png'], getType: async(type) => new Blob(['x'], { type }) },
    ]);
    const manager = await openManager('addImage-0');

    // Shown only to touch pointers; the click works the same either way.
    q(manager, '.paste ol-button').click();

    await vi.waitFor(() => expect(manager._selected).toBe('img:77'));
    const upload = calls.find((c) => c.route === 'POST /books/OL1M/covers/upload.json');
    expect(upload.init.body.get('file').name).toBe('image.png');
});

test('the Paste button explains when the clipboard has no image', async() => {
    seedEditionPage();
    stubFetch({ 'GET /books/OL1M/covers.json': EDITION_STATE });
    vi.spyOn(navigator.clipboard, 'read').mockResolvedValue([{ types: ['text/plain'], getType: async() => new Blob(['hi']) }]);
    const manager = await openManager('addImage-0');

    q(manager, '.paste ol-button').click();

    await vi.waitFor(() => expect(q(manager, '.error')?.textContent).toContain('No image found on your clipboard.'));
    expect(calls.some((c) => c.route.startsWith('POST'))).toBe(false);
});
