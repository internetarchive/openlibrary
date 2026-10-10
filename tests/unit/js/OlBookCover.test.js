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

    test('the hover card carries title, year and author', async() => {
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
        expect(q(el, '.link').contains(slot)).toBe(false);
    });

    test('the hover area spans the overlay, but the link stays the trigger', async() => {
        const el = await mount(
            { src: '/c.jpg', href: '/w' },
            '<button slot="overlay">Save</button>',
        );
        const tip = q(el, 'ol-tooltip');
        expect(tip.contains(q(el, 'slot[name="overlay"]'))).toBe(true);
        await tip.updateComplete;
        expect(tip._triggerEl).toBe(q(el, '.link'));
    });

    test('pressing the overlay hides the card; its popover keeps it off until closed', async() => {
        const el = await mount(
            { src: '/c.jpg', href: '/w' },
            '<button slot="overlay">Save</button>',
        );
        const tip = q(el, 'ol-tooltip');
        const button = el.querySelector('button');
        const hide = vi.spyOn(tip, 'hide');

        button.dispatchEvent(new Event('pointerdown', { bubbles: true, composed: true }));
        expect(hide).toHaveBeenCalledTimes(1);

        button.dispatchEvent(new CustomEvent('ol-popover-open', { bubbles: true, composed: true }));
        expect(tip.disabled).toBe(true);

        const kept = new CustomEvent('ol-popover-close', { bubbles: true, composed: true, cancelable: true });
        kept.preventDefault();
        button.dispatchEvent(kept);
        expect(tip.disabled).toBe(true);

        button.dispatchEvent(new CustomEvent('ol-popover-close', { bubbles: true, composed: true }));
        expect(tip.disabled).toBe(false);
    });
});

describe('ol-book-cover deferred', () => {
    test('a deferred cover holds the image back, keeping its name', async() => {
        const el = await mount({ src: '/covers/1-M.jpg', deferred: true });
        expect(q(el, '.img')).toBeNull();
        expect(q(el, '.blank')).toBeNull();
        expect(q(el, '.pending').getAttribute('aria-label')).toBe('The Two Towers by J.R.R. Tolkien');
    });

    test('removing the attribute loads the image', async() => {
        const el = await mount({ src: '/covers/1-M.jpg', deferred: true });
        el.removeAttribute('deferred');
        await el.updateComplete;
        expect(q(el, '.img').getAttribute('src')).toBe('/covers/1-M.jpg');
        expect(q(el, '.pending')).toBeNull();
    });

    test('a deferred cover with no artwork still draws the blank cover', async() => {
        const el = await mount({ deferred: true });
        expect(q(el, '.blank')).not.toBeNull();
    });
});
