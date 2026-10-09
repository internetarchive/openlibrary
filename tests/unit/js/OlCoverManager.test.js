/**
 * Unit tests for <ol-cover-manager>: what it lists, how picking and removing
 * read in the footer, and the exact payload Save sends. Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlCoverManager.js';

const STATE = {
    key: '/books/OL1M',
    current: 'img:10',
    items: [
        { id: 'suggestion:archive-cover', kind: 'archive_cover', suggestion: 'archive-cover', image_id: null, thumb: 'scan-cover.jpg', removable: false },
        { id: 'suggestion:archive-title', kind: 'archive_title', suggestion: 'archive-title', image_id: null, thumb: 'scan-title.jpg', removable: false },
        { id: 'img:10', kind: 'upload', image_id: 10, thumb: '10-M.jpg', added_by: { key: '/people/ada', name: 'Ada' }, created: '2024-03-02T00:00:00', removable: true },
        { id: 'img:11', kind: 'upload', image_id: 11, thumb: '11-M.jpg', added_by: null, created: null, removable: true },
    ],
};

let calls;

function stubFetch(routes = {}) {
    calls = [];
    global.fetch = vi.fn(async(url, init = {}) => {
        calls.push({ url, init });
        const reply = routes[`${init.method ?? 'GET'} ${url}`] ?? { body: STATE };
        return { ok: reply.ok ?? true, status: reply.ok === false ? 400 : 200, statusText: '', json: async() => reply.body };
    });
}

beforeAll(() => {
    global.URL.createObjectURL = () => 'blob:preview';
    global.URL.revokeObjectURL = () => {};
});

async function mount() {
    const el = document.createElement('ol-cover-manager');
    el.docKey = '/books/OL1M';
    document.body.appendChild(el);
    await vi.waitFor(() => expect(el._loadState).toBe('ready'));
    await el.updateComplete;
    return el;
}

const q = (el, selector) => el.renderRoot.querySelector(selector);
const qa = (el, selector) => [...el.renderRoot.querySelectorAll(selector)];
const status = (el) => q(el, '.status').textContent.trim();
const saveButton = (el) => q(el, 'ol-button[variant="primary"]');

afterEach(() => {
    document.body.innerHTML = '';
});

describe('ol-cover-manager listing', () => {
    test('loads the covers endpoint and lists suggestions before uploads, after the add tile', async() => {
        stubFetch();
        const el = await mount();
        expect(calls[0].url).toBe('/books/OL1M/covers.json');
        expect(q(el, '.add')).not.toBeNull();
        const labels = qa(el, '.pick').map((b) => b.getAttribute('aria-label'));
        expect(labels).toEqual([
            'Internet Archive, Scan · cover page',
            'Internet Archive, Scan · title page',
            'Uploaded, Ada · Mar 2024 (current cover)',
            'Uploaded',
        ]);
    });

    test('author records use the photos endpoint', async() => {
        stubFetch();
        const el = document.createElement('ol-cover-manager');
        el.docKey = '/authors/OL1A';
        document.body.appendChild(el);
        await vi.waitFor(() => expect(calls[0]?.url).toBe('/authors/OL1A/photos.json'));
    });

    test('the current cover starts selected, and Save starts disabled', async() => {
        stubFetch();
        const el = await mount();
        const pressed = qa(el, '.pick').filter((b) => b.getAttribute('aria-pressed') === 'true');
        expect(pressed).toHaveLength(1);
        expect(pressed[0].getAttribute('aria-label')).toContain('current cover');
        expect(saveButton(el).disabled).toBe(true);
    });

    test('a scan page that fails to load is dropped', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.pick img')[1].dispatchEvent(new Event('error'));
        await el.updateComplete;
        expect(qa(el, '.pick')).toHaveLength(3);
    });

    test('a failed load offers a retry', async() => {
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
    test('picking another image says what Save will do', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.pick')[0].click();
        await el.updateComplete;
        expect(status(el)).toBe('When you save, the selected image becomes the cover.');
        expect(saveButton(el).disabled).toBe(false);
    });

    test('suggestions have no Remove; the selected image has none either', async() => {
        stubFetch();
        const el = await mount();
        const removable = qa(el, '.tile').filter((tile) => tile.querySelector('.text-action.danger'));
        expect(removable.map((tile) => tile.querySelector('.pick').getAttribute('aria-label'))).toEqual(['Uploaded']);
    });

    test('the current cover can be removed once something else is picked', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.pick')[0].click();
        await el.updateComplete;
        expect(qa(el, '.tile')[3].querySelector('.text-action.danger')).not.toBeNull();
    });

    test('remove disables the tile and Undo restores it', async() => {
        stubFetch();
        const el = await mount();
        const tile = () => qa(el, '.tile')[4];
        tile().querySelector('.text-action.danger').click();
        await el.updateComplete;
        expect(tile().querySelector('.pick').disabled).toBe(true);
        expect(status(el)).toBe('1 image will be removed.');
        tile().querySelector('.text-action:not(.danger)').click();
        await el.updateComplete;
        expect(tile().querySelector('.pick').disabled).toBe(false);
        expect(saveButton(el).disabled).toBe(true);
    });
});

describe('ol-cover-manager adding', () => {
    const file = (name, type, size = 10) => new File([new Uint8Array(size)], name, { type });

    test('rejects files that are not JPG, GIF, PNG or WebP', async() => {
        stubFetch();
        const el = await mount();
        el._addFiles([file('notes.pdf', 'application/pdf')]);
        await el.updateComplete;
        expect(q(el, '.error').textContent).toContain('JPG, GIF, PNG or WebP');
        expect(calls).toHaveLength(1);
    });

    test('a pasted image uploads and becomes the selection', async() => {
        stubFetch({
            'POST /books/OL1M/covers/upload.json': { body: { id: 'img:99', kind: 'upload', image_id: 99, thumb: '99-M.jpg', added_by: { key: '/people/me', name: 'Me' }, removable: true } },
        });
        const el = await mount();
        const paste = new Event('paste', { cancelable: true });
        paste.clipboardData = { files: [file('image.png', 'image/png')] };
        document.dispatchEvent(paste);
        await vi.waitFor(() => expect(el._selected).toBe('img:99'));
        await el.updateComplete;
        expect(paste.defaultPrevented).toBe(true);
        expect(qa(el, '.pick')[2].getAttribute('aria-label')).toBe('Uploaded, You · just now');
        expect(status(el)).toBe('When you save, the selected image becomes the cover.');
    });

    test('uploads under a neutral filename with the type’s extension', async() => {
        stubFetch();
        const el = await mount();
        el._addFiles([file('Portrait d’Ada\'s.JPEG', 'image/jpeg')]);
        await vi.waitFor(() => expect(calls).toHaveLength(2));
        expect(calls[1].init.body.get('file').name).toBe('image.jpg');
    });

    test('a failed upload drops its placeholder and says so', async() => {
        stubFetch({ 'POST /books/OL1M/covers/upload.json': { ok: false, body: { detail: 'Not a valid image file' } } });
        const el = await mount();
        el._addFiles([file('cover.jpg', 'image/jpeg')]);
        await vi.waitFor(() => expect(el._error).toBe('That image couldn’t be uploaded.'));
        expect(el._added).toHaveLength(0);
    });
});

describe('ol-cover-manager saving', () => {
    test('sends the selection, new uploads and removals, then reports the cover', async() => {
        stubFetch({
            'POST /books/OL1M/covers/upload.json': { body: { id: 'img:99', kind: 'upload', image_id: 99, thumb: '99-M.jpg', removable: true } },
            'POST /books/OL1M/covers.json': { body: { cover_id: 77, state: { ...STATE, current: 'img:77', items: [{ id: 'img:77', image_id: 77, thumb: '77-M.jpg', large: '77-L.jpg' }] } } },
        });
        const el = await mount();
        el._addFiles([new File([new Uint8Array(4)], 'c.jpg', { type: 'image/jpeg' })]);
        await vi.waitFor(() => expect(el._selected).toBe('img:99'));
        el._select(STATE.items[0]);
        el._remove(STATE.items[3]);
        await el.updateComplete;
        expect(status(el)).toBe('When you save, the selected image becomes the cover. 1 new image will be added. 1 image will be removed.');

        const saved = vi.fn();
        el.addEventListener('ol-cover-manager-save', (e) => saved(e.detail));
        await el._save();
        const post = calls.find((c) => c.url === '/books/OL1M/covers.json' && c.init.method === 'POST');
        expect(JSON.parse(post.init.body)).toEqual({ selected: 'suggestion:archive-cover', added: [99], removed: [11] });
        expect(saved).toHaveBeenCalledWith({ coverId: 77, thumb: '77-M.jpg', large: '77-L.jpg' });
    });

    test('a failed save keeps the dialog state and shows an error', async() => {
        stubFetch({ 'POST /books/OL1M/covers.json': { ok: false, body: {} } });
        const el = await mount();
        el._select(STATE.items[1]);
        await el._save();
        await el.updateComplete;
        expect(q(el, '.error').textContent).toContain('couldn’t be saved');
        expect(el._selected).toBe('suggestion:archive-title');
    });
});
