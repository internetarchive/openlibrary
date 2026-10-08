/**
 * Unit tests for <ol-cover-upload>: the form it renders, the label overrides,
 * file/paste selection, the fetch to the existing add-cover endpoint, and the
 * in-page cover refresh that used to be done from inside the add iframe.
 *
 * The DOM-visible success state, real focus, and real file-picker interaction
 * are covered in browser mode. jsdom has no layout and no `navigator.clipboard`.
 */
import '../../../openlibrary/components/lit/OlCoverUpload.js';

// jsdom has no attachInternals; the composed <ol-button>s call it in their
// constructor. Give it a harmless fake, as OLButton.test.js does.
beforeAll(() => {
    HTMLElement.prototype.attachInternals = function() {
        return { form: null };
    };
    URL.createObjectURL = () => 'blob:preview';
    URL.revokeObjectURL = () => {};
});

afterAll(() => {
    delete HTMLElement.prototype.attachInternals;
});

const q = (el, selector) => el.renderRoot.querySelector(selector);

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
    return {
        cover: document.querySelector('.SRPCover'),
        blank: document.querySelector('.SRPCoverBlank'),
        img: document.querySelector('.bookCover img'),
    };
}

function mockFetch(markup, { ok = true } = {}) {
    global.fetch = vi.fn(async() => ({ ok, text: async() => markup }));
    return global.fetch;
}

const SAVED = '<div class="imageSaved" data-image-id="42"><div class="saved">Saved!</div></div>';

async function mount(props = {}) {
    const el = document.createElement('ol-cover-upload');
    Object.assign(
        el,
        {
            action: '/books/OL1M/add-cover',
            docType: '/type/edition',
            coverstoreUrl: 'https://covers.openlibrary.org',
            ...props,
        },
    );
    document.body.appendChild(el);
    await el.updateComplete;
    return el;
}

afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
});

describe('ol-cover-upload form', () => {
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
        const el = await mount({ labels: { upload: 'Téléverser', chooseFile: 'Choisir' } });
        expect(el.renderRoot.textContent).toContain('Téléverser');
        expect(el.renderRoot.textContent).toContain('Choisir');
        expect(el.renderRoot.textContent).not.toContain('Upload');
    });

    test('choosing a file records it and shows a preview', async() => {
        const el = await mount();
        const file = new File(['x'], 'cover.png', { type: 'image/png' });
        el._onFileChange({ target: { files: [file] } });
        await el.updateComplete;
        expect(el._file).toBe(file);
        expect(q(el, '.preview')?.getAttribute('src')).toBe('blob:preview');
    });
});

describe('ol-cover-upload submission', () => {
    test('with no file it reports the problem without calling the server', async() => {
        const el = await mount();
        const fetchMock = mockFetch(SAVED);
        await el._onSubmit();
        await el.updateComplete;
        expect(fetchMock).not.toHaveBeenCalled();
        expect(q(el, '.status--error').textContent).toContain('choose an image');
    });

    test('posts the file and refreshes the page cover on success', async() => {
        seedCover();
        const el = await mount();
        const fetchMock = mockFetch(SAVED);
        el._file = new File(['x'], 'cover.png', { type: 'image/png' });

        const seen = [];
        el.addEventListener('ol-cover-upload', (e) => seen.push(e.detail));
        await el._onSubmit();
        await el.updateComplete;

        const [url, options] = fetchMock.mock.calls[0];
        expect(url).toBe('/books/OL1M/add-cover');
        expect(options.method).toBe('POST');
        expect(options.credentials).toBe('same-origin');
        expect(options.body.get('file')).toBeInstanceOf(File);
        expect(options.body.get('file').name).toBe('cover.png');

        const { cover, blank, img } = {
            cover: document.querySelector('.SRPCover'),
            blank: document.querySelector('.SRPCoverBlank'),
            img: document.querySelector('.bookCover img'),
        };
        expect(img.getAttribute('src')).toBe('https://covers.openlibrary.org/b/id/42-M.jpg');
        expect(img.getAttribute('srcset')).toBe('https://covers.openlibrary.org/b/id/42-M.jpg');
        expect(cover.style.display).toBe('block');
        expect(blank.style.display).toBe('none');
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
        expect(document.querySelector('.SRPCoverBlank').style.display).toBe('block');
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

describe('ol-cover-upload saved state', () => {
    test('shows the saved image, then "add another" returns to the form', async() => {
        const el = await mount();
        mockFetch(SAVED);
        el._file = new File(['x'], 'cover.png', { type: 'image/png' });
        await el._onSubmit();
        await el.updateComplete;

        expect(q(el, '.saved__img').getAttribute('src')).toBe('https://covers.openlibrary.org/b/id/42-M.jpg');
        expect(el.renderRoot.textContent).toContain('Add another image');

        q(el, '.actions ol-button').click();
        await el.updateComplete;
        expect(q(el, '.intro')).not.toBeNull();
        expect(el._savedId).toBeNull();
    });

    test('"finished" closes the enclosing dialog', async() => {
        const dialog = document.createElement('ol-dialog');
        dialog.close = vi.fn();
        document.body.appendChild(dialog);
        const el = document.createElement('ol-cover-upload');
        Object.assign(el, { action: '/x', docType: '/type/work', coverstoreUrl: 'https://c.example' });
        dialog.appendChild(el);
        await el.updateComplete;

        mockFetch(SAVED);
        el._file = new File(['x'], 'c.png', { type: 'image/png' });
        await el._onSubmit();
        await el.updateComplete;

        el.renderRoot.querySelectorAll('.actions ol-button')[1].click();
        expect(dialog.close).toHaveBeenCalledWith('finished');
    });
});

describe('ol-cover-upload clipboard paste', () => {
    function mockClipboard(items) {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { read: vi.fn(async() => items) },
        });
    }

    test('a pasted image is used for the next upload', async() => {
        const el = await mount();
        mockClipboard([
            {
                types: ['image/png'],
                getType: async() => new Blob(['x'], { type: 'image/png' }),
            },
        ]);
        await el._onPaste();
        await el.updateComplete;

        expect(el._file).toBeInstanceOf(File);
        expect(el._file.name).toBe('pasted-image.png');
        expect(q(el, '.preview')?.getAttribute('src')).toBe('blob:preview');
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
});
