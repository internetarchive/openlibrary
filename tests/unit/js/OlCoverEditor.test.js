/**
 * Unit tests for <ol-cover-editor>: the add form (pick / drop / paste / type
 * validation), the external candidates, and the image list (primary, reorder,
 * delete → manage POST). Browser-only behaviour (real picker, real drop,
 * focus) lives in tests/browser/OlCoverEditor.browser.test.js.
 */
import '../../../openlibrary/components/lit/OlCoverEditor.js';

// jsdom has no attachInternals; the composed <ol-button>s call it in their
// constructor. Give it a harmless fake, as OLButton.test.js does.
beforeAll(() => {
    HTMLElement.prototype.attachInternals = function() {
        return { form: null };
    };
    URL.createObjectURL = () => 'blob:preview';
    URL.revokeObjectURL = () => {};
    global.requestAnimationFrame = (fn) => setTimeout(fn, 0);
    // ol-tooltip reads matchMedia to detect a hover-capable pointer.
    window.matchMedia = (query) => ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
    });
});

afterAll(() => {
    delete HTMLElement.prototype.attachInternals;
});

const q = (el, selector) => el.renderRoot.querySelector(selector);
const qa = (el, selector) => [...el.renderRoot.querySelectorAll(selector)];

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

function mockFetch(markup, { ok = true } = {}) {
    global.fetch = vi.fn(async() => ({ ok, text: async() => markup }));
    return global.fetch;
}

const SAVED = '<div class="imageSaved" data-image-id="42"><div class="saved">Saved!</div></div>';

async function mount(props = {}) {
    const el = document.createElement('ol-cover-editor');
    Object.assign(
        el,
        {
            action: '/books/OL1M/add-cover',
            manageUrl: '/books/OL1M/manage-covers',
            docType: '/type/edition',
            coverstoreUrl: 'https://covers.openlibrary.org',
            ...props,
        },
    );
    document.body.appendChild(el);
    // firstUpdated seeds _images from the `images` prop, scheduling a 2nd render.
    await el.updateComplete;
    await el.updateComplete;
    return el;
}

afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
});

describe('ol-cover-editor add form', () => {
    test('renders the intro, a file input, paste and upload actions', async() => {
        const el = await mount();
        expect(q(el, '.intro').textContent).toContain('a few ways to put a cover image');
        expect(q(el, 'input[type="file"]').getAttribute('accept')).toBe('.jpg,.jpeg,.gif,.png,.webp');
        expect(q(el, '.paste-button').textContent).toContain('Paste Image');
        expect(el.renderRoot.textContent).toContain('Upload');
    });

    test('author photos get the author intro and guidelines', async() => {
        const el = await mount({ docType: '/type/author' });
        expect(q(el, '.intro').textContent).toContain('put an author\'s image');
        expect(q(el, '.intro').textContent).toContain('Image Guidelines');
    });

    test('translated labels override the English defaults', async() => {
        const el = await mount({ labels: { upload: 'Téléverser', browse: 'Parcourir' } });
        expect(el.renderRoot.textContent).toContain('Téléverser');
        expect(el.renderRoot.textContent).toContain('Parcourir');
    });

    test('choosing a file records it and shows a preview', async() => {
        const el = await mount();
        const file = new File(['x'], 'cover.png', { type: 'image/png' });
        el._onFileChange({ target: { files: [file] } });
        await el.updateComplete;
        expect(el._file).toBe(file);
        expect(q(el, '.preview')?.getAttribute('src')).toBe('blob:preview');
    });

    test('the preview has a remove control that clears the selection', async() => {
        const el = await mount();
        el._onFileChange({ target: { files: [new File(['x'], 'cover.png', { type: 'image/png' })] } });
        await el.updateComplete;
        expect(q(el, '.preview-clear')).not.toBeNull();

        q(el, '.preview-clear').click();
        await el.updateComplete;
        expect(el._file).toBeNull();
        expect(el._previewUrl).toBe('');
        expect(q(el, '.preview')).toBeNull();
    });

    test('an unsupported file type is rejected and the accepted types are named', async() => {
        const el = await mount();
        el._setFile(new File(['x'], 'notes.txt', { type: 'text/plain' }));
        await el.updateComplete;
        expect(el._file).toBeNull();
        expect(q(el, '.status--error').textContent).toContain('JPG');
    });

    test('an unsupported pasted image is rejected', async() => {
        const el = await mount();
        el._setPastedFile(new File(['x'], 'pasted-image.bmp', { type: 'image/bmp' }));
        await el.updateComplete;
        expect(el._file).toBeNull();
        expect(q(el, '.status--error')).not.toBeNull();
    });

    test('dropping an image selects it', async() => {
        const el = await mount();
        const file = new File(['x'], 'drop.png', { type: 'image/png' });
        el._onDrop({ preventDefault() {}, dataTransfer: { types: ['Files'], files: [file] } });
        await el.updateComplete;
        expect(el._file).toBe(file);
        expect(el._pasted).toBe(false);
        expect(q(el, '.preview')).not.toBeNull();
    });

    test('a drop with no supported image is ignored and explained', async() => {
        const el = await mount();
        el._onDrop({ preventDefault() {}, dataTransfer: { types: ['Files'], files: [new File(['x'], 'a.txt', { type: 'text/plain' })] } });
        await el.updateComplete;
        expect(el._file).toBeNull();
        expect(q(el, '.status--error').textContent).toContain('GIF');
    });

    test('dragging over the dropzone highlights it until the drag leaves', async() => {
        const el = await mount();
        const dt = { types: ['Files'] };
        el._onDragOver({ preventDefault() {}, dataTransfer: dt });
        await el.updateComplete;
        expect(q(el, '.dropzone--active')).not.toBeNull();

        el._onDragLeave({ currentTarget: q(el, '.dropzone'), relatedTarget: null });
        await el.updateComplete;
        expect(q(el, '.dropzone--active')).toBeNull();
    });

    test('an internal image drag does not light up the file dropzone', async() => {
        const el = await mount();
        el._onDragOver({ preventDefault() {}, dataTransfer: { types: ['text/plain'] } });
        await el.updateComplete;
        expect(q(el, '.dropzone--active')).toBeNull();
    });
});

describe('ol-cover-editor submission', () => {
    test('with no file it reports the problem without calling the server', async() => {
        const el = await mount();
        const fetchMock = mockFetch(SAVED);
        await el._onSubmit();
        await el.updateComplete;
        expect(fetchMock).not.toHaveBeenCalled();
        expect(q(el, '.status--error').textContent).toContain('choose an image');
    });

    test('posts the file, adds it to the list and refreshes the page cover', async() => {
        seedCover();
        const el = await mount();
        const fetchMock = mockFetch(SAVED);
        el._file = new File(['x'], 'cover.png', { type: 'image/png' });

        const seen = [];
        el.addEventListener('ol-cover-editor-add', (e) => seen.push(e.detail));
        await el._onSubmit();
        await el.updateComplete;

        const [url, options] = fetchMock.mock.calls[0];
        expect(url).toBe('/books/OL1M/add-cover');
        expect(options.method).toBe('POST');
        expect(options.credentials).toBe('same-origin');
        expect(options.body.get('file').name).toBe('cover.png');

        expect(el._images.map((i) => i.id)).toEqual([42]);
        expect(q(el, '.image--primary')).not.toBeNull();
        expect(q(el, '.status').textContent).toContain('Image added');
        expect(document.querySelector('.bookCover img').getAttribute('src')).toBe(
            'https://covers.openlibrary.org/b/id/42-M.jpg',
        );
        expect(document.querySelector('.SRPCover').style.display).toBe('block');
        expect(document.querySelector('.SRPCoverBlank').style.display).toBe('none');
        expect(seen).toEqual([{ id: 42 }]);
    });

    test('author photos refresh src only, leaving the blank panel alone', async() => {
        seedCover();
        const el = await mount({ docType: '/type/author', action: '/authors/OL1A/add-photo' });
        mockFetch(SAVED);
        el._file = new File(['x'], 'photo.png', { type: 'image/png' });
        await el._onSubmit();

        const img = document.querySelector('.bookCover img');
        expect(img.getAttribute('src')).toBe('https://covers.openlibrary.org/a/id/42-M.jpg');
        expect(img.hasAttribute('srcset')).toBe(false);
    });

    test('an error response shows a message and leaves the cover untouched', async() => {
        seedCover();
        const el = await mount();
        mockFetch('<div class="popAlert"></div>');
        el._file = new File(['x'], 'cover.png', { type: 'image/png' });
        await el._onSubmit();
        await el.updateComplete;

        expect(q(el, '.status--error').textContent).toContain('Could not upload');
        expect(document.querySelector('.bookCover img').getAttribute('src')).toBe('/old-M.jpg');
    });

    test('a rejected request is caught and reported', async() => {
        const el = await mount();
        global.fetch = vi.fn(async() => {
            throw new Error('offline');
        });
        el._file = new File(['x'], 'cover.png', { type: 'image/png' });
        await el._onSubmit();
        await el.updateComplete;
        expect(q(el, '.status--error').textContent).toContain('Could not upload');
    });
});

describe('ol-cover-editor external images', () => {
    test('renders server-supplied candidates grouped by source', async() => {
        const el = await mount({
            candidates: [
                { url: 'https://commons.example/a.jpg', source: 'Wikidata' },
                { url: 'https://archive.org/download/x/page/cover', source: 'Internet Archive' },
            ],
        });
        const imgs = qa(el, '.candidate__img').map((i) => i.getAttribute('src'));
        expect(imgs).toEqual(['https://commons.example/a.jpg', 'https://archive.org/download/x/page/cover']);
        const headings = qa(el, '.heading').map((h) => h.textContent);
        expect(headings).toContain('Or, use an image from Wikidata');
        expect(headings).toContain('Or, use an image from Internet Archive');
    });

    test('importing an external image posts its URL and adds it', async() => {
        seedCover();
        const el = await mount({ candidates: [{ url: 'https://commons.example/a.jpg', source: 'Wikidata' }] });
        const fetchMock = mockFetch(SAVED);
        await el._useUrl('https://commons.example/a.jpg');
        await el.updateComplete;

        const [url, options] = fetchMock.mock.calls[0];
        expect(url).toBe('/books/OL1M/add-cover');
        expect(options.body.get('url')).toBe('https://commons.example/a.jpg');
        expect(el._images.map((i) => i.id)).toEqual([42]);
    });
});

describe('ol-cover-editor clipboard paste', () => {
    function mockClipboard(items) {
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { read: vi.fn(async() => items) } });
    }

    test('a pasted image is used for the next upload', async() => {
        const el = await mount();
        mockClipboard([{ types: ['image/png'], getType: async() => new Blob(['x'], { type: 'image/png' }) }]);
        await el._onPaste();
        await el.updateComplete;
        expect(el._file).toBeInstanceOf(File);
        expect(el._file.name).toBe('pasted-image.png');
        expect(q(el, '.paste-button').textContent).toContain('Change Image');
    });

    test('a clipboard without an image reports it', async() => {
        const el = await mount();
        mockClipboard([{ types: ['text/plain'], getType: async() => new Blob(['x']) }]);
        await el._onPaste();
        await el.updateComplete;
        expect(q(el, '.status--error').textContent).toContain('No image found');
        expect(el._file).toBeNull();
    });

    test('an image pasted with the keyboard is used for the next upload', async() => {
        const el = await mount();
        const file = new File(['x'], 'shot.png', { type: 'image/png' });
        let prevented = false;
        el._onPasteEvent({
            clipboardData: { items: [{ kind: 'file', type: 'image/png', getAsFile: () => file }] },
            preventDefault: () => {
                prevented = true;
            },
        });
        await el.updateComplete;
        expect(prevented).toBe(true);
        expect(el._file).toBe(file);
        expect(el._pasted).toBe(true);
    });

    test('a paste is ignored while the dialog is closed', async() => {
        const dialog = document.createElement('ol-dialog');
        document.body.appendChild(dialog);
        const el = document.createElement('ol-cover-editor');
        Object.assign(el, { action: '/x', docType: '/type/edition', coverstoreUrl: 'https://c.example' });
        dialog.appendChild(el);
        await el.updateComplete;

        el._onPasteEvent({
            clipboardData: { items: [{ kind: 'file', type: 'image/png', getAsFile: () => new File(['x'], 'a.png', { type: 'image/png' }) }] },
            preventDefault() {},
        });
        expect(el._file).toBeNull();
    });
});

describe('ol-cover-editor image management', () => {
    const IMAGES = [
        { id: 1, url: 'https://covers.openlibrary.org/b/id/1-M.jpg' },
        { id: 2, url: 'https://covers.openlibrary.org/b/id/2-M.jpg' },
        { id: 3, url: 'https://covers.openlibrary.org/b/id/3-M.jpg' },
    ];

    function manageFetch() {
        global.fetch = vi.fn(async() => ({ ok: true, text: async() => '' }));
        return global.fetch;
    }

    test('renders the current images with the first marked primary and a trash target', async() => {
        const el = await mount({ images: IMAGES });
        expect(qa(el, '.image').length).toBe(3);
        expect(q(el, '.image--primary .image__img').getAttribute('src')).toBe(IMAGES[0].url);
        expect(q(el, '.trash')).not.toBeNull();
    });

    test('dragging an image onto the trash removes it', async() => {
        const el = await mount({ images: IMAGES });
        const fetchMock = manageFetch();
        const dt = { effectAllowed: '', dropEffect: '', setData() {} };
        el._onCardDragStart({ dataTransfer: dt }, 0);
        el._onTrashDragOver({ preventDefault() {}, dataTransfer: dt });
        await el.updateComplete;
        expect(q(el, '.trash--active')).not.toBeNull();

        el._onTrashDrop({ preventDefault() {}, dataTransfer: dt });
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([2, 3]);
        expect(fetchMock).toHaveBeenCalled();
    });

    test('the Delete key removes a focused image', async() => {
        const el = await mount({ images: IMAGES });
        manageFetch();
        el._onCardKeydown({ key: 'Delete', preventDefault() {} }, 1);
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([1, 3]);
    });

    test('clicking an image makes it primary', async() => {
        const el = await mount({ images: IMAGES });
        const fetchMock = manageFetch();
        el._onCardClick(2);
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([3, 1, 2]);
        expect(fetchMock).toHaveBeenCalled();
    });

    test('deleting offers an undo that restores the image at its position', async() => {
        seedCover();
        const el = await mount({ images: IMAGES });
        manageFetch();
        el._deleteImage(1);
        await new Promise((resolve) => setTimeout(resolve, 0));
        await el.updateComplete;

        expect(el._images.map((i) => i.id)).toEqual([1, 3]);
        expect(el.renderRoot.textContent).toContain('Image removed');
        const undo = q(el, '.status__undo');
        expect(undo).not.toBeNull();

        undo.click();
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([1, 2, 3]);
    });

    test('Cmd+Z undoes the last reorder', async() => {
        const el = await mount({ images: IMAGES });
        manageFetch();
        el._onCardClick(2);
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([3, 1, 2]);

        el._onKeydown({ metaKey: true, key: 'z', target: document.body, preventDefault() {} });
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([1, 2, 3]);
    });

    test('Cmd+Z steps back through several changes', async() => {
        const el = await mount({ images: IMAGES });
        manageFetch();
        el._onCardClick(2);
        await el.updateComplete;
        el._deleteImage(0);
        await el.updateComplete;

        el._onKeydown({ metaKey: true, key: 'z', target: document.body, preventDefault() {} });
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([3, 1, 2]);

        el._onKeydown({ metaKey: true, key: 'z', target: document.body, preventDefault() {} });
        await el.updateComplete;
        expect(el._images.map((i) => i.id)).toEqual([1, 2, 3]);
    });

    test('Cmd+Z does nothing without history', async() => {
        const el = await mount({ images: IMAGES });
        const fetchMock = manageFetch();
        el._onKeydown({ metaKey: true, key: 'z', target: document.body, preventDefault() {} });
        await el.updateComplete;
        expect(fetchMock).not.toHaveBeenCalled();
        expect(el._images.map((i) => i.id)).toEqual([1, 2, 3]);
    });

    test('make primary moves an image to the front and saves the order', async() => {
        const el = await mount({ images: IMAGES });
        const fetchMock = manageFetch();
        el._makePrimary(2);
        await el.updateComplete;

        expect(el._images.map((i) => i.id)).toEqual([3, 1, 2]);
        expect(fetchMock.mock.calls[0][0]).toBe('/books/OL1M/manage-covers');
        expect(fetchMock.mock.calls[0][1].body.getAll('image')).toEqual(['3', '1', '2', '-1', '-']);
    });

    test('deleting an image removes it and saves the order', async() => {
        const el = await mount({ images: IMAGES });
        const fetchMock = manageFetch();
        el._deleteImage(0);
        await el.updateComplete;

        expect(el._images.map((i) => i.id)).toEqual([2, 3]);
        expect(fetchMock.mock.calls[0][1].body.getAll('image')).toEqual(['2', '3', '-1', '-']);
    });

    test('arrow keys reorder an image and save', async() => {
        const el = await mount({ images: IMAGES });
        const fetchMock = manageFetch();
        el._onCardKeydown({ key: 'ArrowRight', preventDefault() {} }, 0);
        await el.updateComplete;

        expect(el._images.map((i) => i.id)).toEqual([2, 1, 3]);
        expect(fetchMock).toHaveBeenCalled();
    });

    test('dragging an image onto another reorders and saves', async() => {
        const el = await mount({ images: IMAGES });
        const fetchMock = manageFetch();
        const dt = { effectAllowed: '', dropEffect: '', setData() {} };
        el._onCardDragStart({ dataTransfer: dt }, 0);
        el._onCardDrop({ preventDefault() {}, dataTransfer: dt }, 2);
        await el.updateComplete;

        expect(el._images.map((i) => i.id)).toEqual([2, 3, 1]);
        expect(fetchMock).toHaveBeenCalled();
    });

    test('clearing every image falls back to the blank cover', async() => {
        seedCover();
        const el = await mount({ images: [{ id: 9, url: 'u9' }] });
        manageFetch();
        el._deleteImage(0);
        await el.updateComplete;

        expect(el._images).toEqual([]);
        expect(document.querySelector('.SRPCover').style.display).toBe('none');
        expect(document.querySelector('.SRPCoverBlank').style.display).toBe('block');
    });

    test('a failed save reports an error', async() => {
        const el = await mount({ images: IMAGES });
        global.fetch = vi.fn(async() => ({ ok: false, text: async() => '' }));
        el._deleteImage(0);
        await el.updateComplete;
        await Promise.resolve();
        await el.updateComplete;
        expect(q(el, '.status--error').textContent).toContain('Could not save');
    });
});
