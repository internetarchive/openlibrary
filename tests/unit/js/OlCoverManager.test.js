/**
 * Unit tests for <ol-cover-manager>: what it lists, when replacing a cover asks
 * why, how picking and removing read in the footer, and the exact payload Save
 * sends. Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlCoverManager.js';

const STATE = {
    key: '/books/OL1M',
    current: 'img:10',
    items: [
        { id: 'suggestion:archive-cover', kind: 'archive_cover', suggestion: 'archive-cover', image_id: null, thumb: 'scan-cover.jpg' },
        { id: 'suggestion:archive-title', kind: 'archive_title', suggestion: 'archive-title', image_id: null, thumb: 'scan-title.jpg' },
        { id: 'img:10', kind: 'upload', image_id: 10, thumb: '10-M.jpg', added_by: { key: '/people/ada', name: 'Ada' }, created: '2024-03-02T00:00:00' },
        { id: 'img:11', kind: 'upload', image_id: 11, thumb: '11-M.jpg', added_by: null, created: null }
    ]
};

/** An edition with no cover of its own: the page shows its Internet Archive scan. */
const FALLBACK = {
    key: '/books/OL1M',
    current: 'suggestion:archive-cover',
    items: STATE.items.slice(0, 2)
};

const NO_COVER = {
    key: '/books/OL1M',
    current: null,
    items: [{ id: 'suggestion:amazon', kind: 'amazon', suggestion: 'amazon', image_id: null, thumb: 'amazon.jpg', isbn: '0140449132' }]
};

const UPLOADED = { id: 'img:99', kind: 'upload', image_id: 99, thumb: '99-M.jpg', added_by: { key: '/people/me', name: 'Me' } };

let calls;

function stubFetch(routes = {}) {
    calls = [];
    global.fetch = vi.fn(async (url, init = {}) => {
        calls.push({ url, init });
        const reply = routes[`${init.method ?? 'GET'} ${url}`] ?? { body: STATE };
        return { ok: reply.ok ?? true, status: reply.ok === false ? 400 : 200, statusText: '', json: async () => reply.body };
    });
}

beforeAll(() => {
    global.URL.createObjectURL = () => 'blob:preview';
    global.URL.revokeObjectURL = () => {};
});

const q = (el, selector) => el.renderRoot.querySelector(selector);
const qa = (el, selector) => [...el.renderRoot.querySelectorAll(selector)];
const status = el => q(el, '.status').textContent.trim();
const saveButton = el => q(el, 'ol-button[variant="primary"]');
const picks = el => qa(el, '.row:not(.upload) .option');
const rows = el => qa(el, '.row:not(.upload)');
const file = (name, type, size = 10) => new File([new Uint8Array(size)], name, { type });

async function chooseReason(el, value, note) {
    q(el, `.chip[data-value="${value}"]`).click();
    await el.updateComplete;
    await el.updateComplete;
    if (note !== undefined) {
        const input = q(el, '.note input');
        input.value = note;
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
    }
}

async function mount(docKey = '/books/OL1M') {
    const el = document.createElement('ol-cover-manager');
    el.docKey = docKey;
    document.body.appendChild(el);
    await vi.waitFor(() => expect(el._loadState).toBe('ready'));
    await el.updateComplete;
    return el;
}

afterEach(() => {
    document.body.innerHTML = '';
});

describe('ol-cover-manager listing', () => {
    test('loads the covers endpoint and lists suggestions before uploads, after the upload row', async () => {
        stubFetch();
        const el = await mount();
        expect(calls[0].url).toBe('/books/OL1M/covers.json');
        expect(q(el, '.options > li').classList.contains('upload')).toBe(true);
        const labels = picks(el).map(b => b.getAttribute('aria-label'));
        expect(labels).toEqual([
            'Scan of the cover, Internet Archive',
            'Scan of the title page, Internet Archive',
            'Uploaded by Ada, March 2024 (current cover)',
            'Uploaded image'
        ]);
    });

    test('Amazon’s cover is tagged by source, and is dropped when Amazon has none', async () => {
        stubFetch({ 'GET /books/OL1M/covers.json': { body: NO_COVER } });
        const el = await mount();
        expect(picks(el).map(b => b.getAttribute('aria-label'))).toEqual(['Cover from Amazon, Amazon']);
        const img = q(el, '.row:not(.upload) img');
        Object.defineProperty(img, 'naturalWidth', { value: 1 });
        img.dispatchEvent(new Event('load'));
        await el.updateComplete;
        expect(picks(el)).toHaveLength(0);
    });

    test('author records use the photos endpoint', async () => {
        stubFetch();
        const el = document.createElement('ol-cover-manager');
        el.docKey = '/authors/OL1A';
        document.body.appendChild(el);
        await vi.waitFor(() => expect(calls[0]?.url).toBe('/authors/OL1A/photos.json'));
    });

    test('opens on the list with the current cover selected, shown large, and nothing asked', async () => {
        stubFetch();
        const el = await mount();
        const pressed = picks(el).filter(b => b.getAttribute('aria-pressed') === 'true');
        expect(pressed).toHaveLength(1);
        expect(pressed[0].getAttribute('aria-label')).toContain('current cover');
        expect(q(el, '#cover-heading').textContent).toBe('Current cover');
        expect(q(el, '.panel .overline').textContent).toBe('Choose the new cover');
        expect(q(el, '.why')).toBeNull();
        expect(status(el)).toBe('');
        expect(saveButton(el).disabled).toBe(true);
    });

    test('a book without a cover is one column until something is picked', async () => {
        stubFetch({ 'GET /books/OL1M/covers.json': { body: NO_COVER } });
        const el = await mount();
        expect(q(el, '.layout').classList.contains('single')).toBe(true);
        expect(q(el, '.cover')).toBeNull();
        expect(q(el, '.panel > h3').textContent).toBe('This edition has no cover');
        picks(el)[0].click();
        await el.updateComplete;
        expect(q(el, '.layout').classList.contains('single')).toBe(false);
        expect(q(el, '#cover-heading').textContent).toBe('New cover');
        expect(q(el, '.why')).toBeNull();
        expect(saveButton(el).disabled).toBe(false);
    });

    test('a scan page that fails to load is dropped', async () => {
        stubFetch();
        const el = await mount();
        qa(el, '.row:not(.upload) img')[1].dispatchEvent(new Event('error'));
        await el.updateComplete;
        expect(picks(el)).toHaveLength(3);
    });

    test('a failed load offers a retry', async () => {
        stubFetch({ 'GET /books/OL1M/covers.json': { ok: false, body: {} } });
        const el = document.createElement('ol-cover-manager');
        el.docKey = '/books/OL1M';
        document.body.appendChild(el);
        await vi.waitFor(() => expect(el._loadState).toBe('error'));
        await el.updateComplete;
        expect(q(el, '[role="alert"]').textContent).toContain('couldn’t be loaded');
    });
});

describe('ol-cover-manager choosing and removing', () => {
    test('picking another image previews it as the new cover, and Keep current undoes it', async () => {
        stubFetch();
        const el = await mount();
        picks(el)[0].click();
        await el.updateComplete;
        expect(q(el, '#cover-heading').textContent).toBe('New cover');
        expect(q(el, '.cover-frame img').getAttribute('src')).toBe('scan-cover.jpg');
        q(el, '.band .keep').click();
        await el.updateComplete;
        expect(el._selected).toBe('img:10');
        expect(q(el, '#cover-heading').textContent).toBe('Current cover');
        expect(q(el, '.why')).toBeNull();
    });

    test('suggestions have no Remove; the selected image has none either', async () => {
        stubFetch();
        const el = await mount();
        const removable = rows(el).filter(row => row.querySelector('.text-action.danger'));
        expect(removable.map(row => row.querySelector('.option').getAttribute('aria-label'))).toEqual(['Uploaded image']);
    });

    test('the current cover can be removed once something else is picked', async () => {
        stubFetch();
        const el = await mount();
        picks(el)[0].click();
        await el.updateComplete;
        expect(rows(el)[2].querySelector('.text-action.danger')).not.toBeNull();
    });

    test('remove disables the tile and Undo restores it, with no reason asked', async () => {
        stubFetch();
        const el = await mount();
        const row = () => rows(el)[3];
        row().querySelector('.text-action.danger').click();
        await el.updateComplete;
        expect(row().querySelector('.option').disabled).toBe(true);
        expect(status(el)).toBe('1 image will be removed.');
        expect(q(el, '.why')).toBeNull();
        expect(saveButton(el).disabled).toBe(false);
        row().querySelector('.text-action:not(.danger)').click();
        await el.updateComplete;
        expect(row().querySelector('.option').disabled).toBe(false);
        expect(saveButton(el).disabled).toBe(true);
    });
});

describe('ol-cover-manager asking why', () => {
    test('replacing a book’s own cover asks why in the band under the columns, and Save waits for an answer', async () => {
        stubFetch();
        const el = await mount();
        picks(el)[1].click();
        await el.updateComplete;
        expect(q(el, '.band .why')).not.toBeNull();
        expect(qa(el, '.chip').map(c => c.textContent.trim())).toEqual(['Wrong cover', 'Better image', 'Not the front cover', 'Something else']);
        expect(status(el)).toBe('');
        expect(saveButton(el).disabled).toBe(true);
        await chooseReason(el, 'not_front');
        expect(q(el, '.chip[aria-pressed="true"]').dataset.value).toBe('not_front');
        expect(q(el, '.reason-hint').textContent).toContain('title page');
        expect(status(el)).toBe('');
        expect(saveButton(el).disabled).toBe(false);
    });

    test('“Something else” opens a note and needs a few words', async () => {
        stubFetch();
        const el = await mount();
        picks(el)[0].click();
        await el.updateComplete;
        await chooseReason(el, 'other');
        expect(el.renderRoot.activeElement).toBe(q(el, '.note input'));
        expect(q(el, '.reason-hint')).toBeNull();
        expect(saveButton(el).disabled).toBe(true);
        await chooseReason(el, 'other', 'Movie tie-in');
        expect(saveButton(el).disabled).toBe(false);
    });

    test('adding a spare image beside the current cover never asks', async () => {
        stubFetch({ 'POST /books/OL1M/covers/upload.json': { body: UPLOADED } });
        const el = await mount();
        el._addFiles([file('c.jpg', 'image/jpeg')]);
        await vi.waitFor(() => expect(el._selected).toBe('img:99'));
        await el.updateComplete;
        // The upload is picked as the new cover, so the question appears; keeping the current cover withdraws it.
        expect(q(el, '.why')).not.toBeNull();
        q(el, '.band .keep').click();
        await el.updateComplete;
        expect(q(el, '.why')).toBeNull();
        expect(status(el)).toBe('1 new image will be added.');
        expect(saveButton(el).disabled).toBe(false);
    });

    test('a record showing a borrowed scan is adding a cover, not changing one', async () => {
        stubFetch({ 'GET /books/OL1M/covers.json': { body: FALLBACK } });
        const el = await mount();
        expect(q(el, '#cover-heading').textContent).toBe('Current cover');
        expect(q(el, '.note-text').textContent).toContain('no cover of its own');
        expect(q(el, '.panel .overline').textContent).toBe('Choose a cover');
        picks(el)[1].click();
        await el.updateComplete;
        expect(q(el, '.band .keep')).not.toBeNull();
        expect(q(el, '.why')).toBeNull();
        expect(saveButton(el).disabled).toBe(false);
    });

    test('an author photo never asks', async () => {
        stubFetch({
            'GET /authors/OL1A/photos.json': {
                body: {
                    key: '/authors/OL1A',
                    current: 'img:5',
                    items: [
                        { id: 'img:5', kind: 'upload', image_id: 5, thumb: '5.jpg' },
                        { id: 'img:6', kind: 'upload', image_id: 6, thumb: '6.jpg' }
                    ]
                }
            }
        });
        const el = await mount('/authors/OL1A');
        picks(el)[1].click();
        await el.updateComplete;
        expect(q(el, '.why')).toBeNull();
        expect(saveButton(el).disabled).toBe(false);
    });

    test('titles the dialog for adding when the record has no image of its own', async () => {
        stubFetch({ 'GET /books/OL1M/covers.json': { body: FALLBACK } });
        // ol-dialog isn't registered here; an open stand-in is enough for the manager to load and title it.
        const dialog = document.createElement('ol-dialog');
        dialog.open = true;
        const el = document.createElement('ol-cover-manager');
        el.docKey = '/books/OL1M';
        dialog.appendChild(el);
        document.body.appendChild(dialog);
        await vi.waitFor(() => expect(el._loadState).toBe('ready'));
        expect(dialog.label).toBe('Add a cover');
    });
});

describe('ol-cover-manager adding', () => {
    test('rejects files that are not JPG, GIF, PNG or WebP', async () => {
        stubFetch();
        const el = await mount();
        el._addFiles([file('notes.pdf', 'application/pdf')]);
        await el.updateComplete;
        expect(q(el, '.error').textContent).toContain('JPG, GIF, PNG or WebP');
        expect(calls).toHaveLength(1);
    });

    test('a pasted image uploads and becomes the selection', async () => {
        stubFetch({ 'POST /books/OL1M/covers/upload.json': { body: UPLOADED } });
        const el = await mount();
        const paste = new Event('paste', { cancelable: true });
        paste.clipboardData = { files: [file('image.png', 'image/png')] };
        document.dispatchEvent(paste);
        await vi.waitFor(() => expect(el._selected).toBe('img:99'));
        await el.updateComplete;
        expect(paste.defaultPrevented).toBe(true);
        expect(picks(el)[2].getAttribute('aria-label')).toBe('Your upload, Just now');
        expect(q(el, '#cover-heading').textContent).toBe('New cover');
    });

    test('uploads under a neutral filename with the type’s extension', async () => {
        stubFetch();
        const el = await mount();
        el._addFiles([file("Portrait d’Ada's.JPEG", 'image/jpeg')]);
        await vi.waitFor(() => expect(calls).toHaveLength(2));
        expect(calls[1].init.body.get('file').name).toBe('image.jpg');
    });

    test('a failed upload drops its placeholder and says so', async () => {
        stubFetch({ 'POST /books/OL1M/covers/upload.json': { ok: false, body: { detail: 'Not a valid image file' } } });
        const el = await mount();
        el._addFiles([file('cover.jpg', 'image/jpeg')]);
        await vi.waitFor(() => expect(el._error).toBe('That image couldn’t be uploaded.'));
        expect(el._added).toHaveLength(0);
    });
});

describe('ol-cover-manager saving', () => {
    test('sends the selection, new uploads, removals and the reason, then reports the cover', async () => {
        stubFetch({
            'POST /books/OL1M/covers/upload.json': { body: { id: 'img:99', kind: 'upload', image_id: 99, thumb: '99-M.jpg' } },
            'POST /books/OL1M/covers.json': { body: { cover_id: 77 } }
        });
        const el = await mount();
        el._addFiles([file('c.jpg', 'image/jpeg')]);
        await vi.waitFor(() => expect(el._selected).toBe('img:99'));
        el._select(STATE.items[0]);
        el._remove(STATE.items[3]);
        await el.updateComplete;
        await chooseReason(el, 'wrong');
        expect(status(el)).toBe('1 new image will be added. 1 image will be removed.');

        const saved = vi.fn();
        el.addEventListener('ol-cover-manager-save', e => saved(e.detail));
        await el._save();
        const post = calls.find(c => c.url === '/books/OL1M/covers.json' && c.init.method === 'POST');
        expect(JSON.parse(post.init.body)).toEqual({ suggestion: 'archive-cover', added: [99], removed: [11], reason: 'wrong' });
        expect(saved).toHaveBeenCalledWith({ coverId: 77 });
    });

    test('“Something else” sends its note', async () => {
        stubFetch({ 'POST /books/OL1M/covers.json': { body: { cover_id: 10 } } });
        const el = await mount();
        el._select(STATE.items[1]);
        await el.updateComplete;
        await chooseReason(el, 'other', '  Movie tie-in ');
        await el._save();
        const post = calls.find(c => c.init.method === 'POST');
        expect(JSON.parse(post.init.body)).toMatchObject({ suggestion: 'archive-title', reason: 'other', reason_note: 'Movie tie-in' });
    });

    test('Save does nothing until the reason is given', async () => {
        stubFetch({ 'POST /books/OL1M/covers.json': { body: { cover_id: 10 } } });
        const el = await mount();
        el._select(STATE.items[1]);
        await el.updateComplete;
        await el._save();
        expect(calls.some(c => c.init.method === 'POST')).toBe(false);
    });

    test('a change that keeps the cover sends no reason', async () => {
        stubFetch({ 'POST /books/OL1M/covers.json': { body: { cover_id: 10 } } });
        const el = await mount();
        el._remove(STATE.items[3]);
        await el.updateComplete;
        await el._save();
        const post = calls.find(c => c.init.method === 'POST');
        expect(JSON.parse(post.init.body)).toEqual({ image_id: 10, added: [], removed: [11] });
    });

    test('a failed save keeps the dialog state and shows an error', async () => {
        stubFetch({ 'POST /books/OL1M/covers.json': { ok: false, body: {} } });
        const el = await mount();
        el._select(STATE.items[1]);
        await el.updateComplete;
        await chooseReason(el, 'better');
        await el._save();
        await el.updateComplete;
        expect(q(el, '.error').textContent).toContain('couldn’t be saved');
        expect(el._selected).toBe('suggestion:archive-title');
        expect(el._reason).toBe('better');
    });
});
