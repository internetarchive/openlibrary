/**
 * Unit tests for <ol-book-cover>: the artwork/blank-cover branch, the
 * accessible name, the optional hover card, and the overlay corner.
 */
import '../../../openlibrary/components/lit/OlBookCover.js';

beforeAll(() => {
    // ol-tooltip reads matchMedia to detect a hover-capable pointer.
    window.matchMedia = query => ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
    });
});

async function mount(props = {}, inner = '') {
    const el = document.createElement('ol-book-cover');
    Object.assign(el, { bookTitle: 'The Two Towers', authors: 'J.R.R. Tolkien', ...props });
    el.innerHTML = inner;
    document.body.appendChild(el);
    await el.updateComplete;
    return el;
}

const q = (el, selector) => el.renderRoot.querySelector(selector);

afterEach(() => {
    document.body.innerHTML = '';
});

describe('ol-book-cover artwork', () => {
    test('a src renders the image, lazily, with title and author as its name', async() => {
        const el = await mount({ src: '/covers/1-M.jpg' });
        const img = q(el, '.img');
        expect(img.getAttribute('src')).toBe('/covers/1-M.jpg');
        expect(img.getAttribute('loading')).toBe('lazy');
        expect(img.getAttribute('alt')).toBe('The Two Towers by J.R.R. Tolkien');
        expect(q(el, '.blank')).toBeNull();
    });

    test('no src draws the blank cover, still named for a screen reader', async() => {
        const el = await mount();
        const blank = q(el, '.blank');
        expect(blank.getAttribute('role')).toBe('img');
        expect(blank.getAttribute('aria-label')).toBe('The Two Towers by J.R.R. Tolkien');
        expect(q(el, '.blank__title').textContent).toBe('The Two Towers');
        expect(q(el, '.blank__author').textContent).toBe('J.R.R. Tolkien');
    });

    test('a small blank cover drops the author, which has no room', async() => {
        const el = await mount({ size: 'small' });
        expect(q(el, '.blank__title')).not.toBeNull();
        expect(q(el, '.blank__author')).toBeNull();
    });

    test('with no author the name is the title alone', async() => {
        const el = await mount({ src: '/c.jpg', authors: '' });
        expect(q(el, '.img').getAttribute('alt')).toBe('The Two Towers');
    });

    test('labels override the byline joiner used in the accessible name', async() => {
        const el = await mount({ src: '/c.jpg', labels: { by: 'par %(name)s' } });
        expect(q(el, '.img').getAttribute('alt')).toBe('The Two Towers par J.R.R. Tolkien');
    });
});

describe('ol-book-cover link and hover card', () => {
    test('an href wraps the artwork in a link and reports the click', async() => {
        const el = await mount({ src: '/c.jpg', href: '/works/OL1W' });
        const link = q(el, '.link');
        expect(link.getAttribute('href')).toBe('/works/OL1W');

        const seen = [];
        el.addEventListener('ol-book-cover-click', e => seen.push(e.detail));
        link.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        expect(seen).toEqual([{ href: '/works/OL1W' }]);
    });

    test('without an href the artwork is not a link', async() => {
        const el = await mount({ src: '/c.jpg' });
        expect(q(el, '.link')).toBeNull();
        expect(q(el, '.img')).not.toBeNull();
    });

    test('the hover card carries title, year and author, and wraps the link only', async() => {
        const el = await mount({ src: '/c.jpg', href: '/works/OL1W', year: '1954' });
        const tip = q(el, 'ol-tooltip');
        expect(tip.querySelector('.link')).not.toBeNull();
        expect(tip.querySelector('[slot="content"]').textContent.replace(/\s+/g, ' ').trim())
            .toBe('The Two Towers (1954) J.R.R. Tolkien');
    });

    test('a book with no year shows the title alone in the hover card', async() => {
        const el = await mount({ src: '/c.jpg', href: '/w', authors: '' });
        expect(q(el, '.tip__year')).toBeNull();
        expect(q(el, '.tip__byline')).toBeNull();
        expect(q(el, '.tip__title').textContent).toBe('The Two Towers');
    });
});

describe('ol-book-cover overlay', () => {
    test('slotted content takes the corner and stays outside the link', async() => {
        const el = await mount(
            { src: '/c.jpg', href: '/w' },
            '<button slot="overlay">Save</button>',
        );
        const slot = q(el, 'slot[name="overlay"]');
        expect(slot.assignedElements()[0].textContent).toBe('Save');
        // The tooltip wraps the link only, so hovering the save button is not
        // hovering the cover.
        expect(q(el, 'ol-tooltip').contains(slot)).toBe(false);
    });
});
