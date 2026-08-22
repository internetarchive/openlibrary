/**
 * Unit tests for <ol-shelf-button>: the two shapes, the signed-out branch, and
 * the statelessness that matters most — it reports a shelf change and never
 * writes its own `shelf`, so the surface that owns the book stays the one
 * source of truth. Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlShelfButton.js';
import { SHELF } from '../../../openlibrary/components/lit/utils/books-api.js';

let fetchCalls;

function stubFetch({ ok = true, status = 200 } = {}) {
    fetchCalls = [];
    global.fetch = jest.fn(async(url, init) => {
        fetchCalls.push({ url, init });
        return { ok, status, json: async() => ({ bookshelves_affected: 1 }) };
    });
}

beforeAll(() => {
    window.matchMedia = query => ({
        matches: false, media: query,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {},
    });
    global.ResizeObserver = class { observe() {} disconnect() {} };
});

async function mount(props = {}) {
    const el = document.createElement('ol-shelf-button');
    Object.assign(el, {
        workKey: '/works/OL1W',
        editionKey: 'OL1M',
        bookTitle: 'The Two Towers',
        shelf: null,
        rating: null,
        ...props,
    });
    document.body.appendChild(el);
    await el.updateComplete;
    return el;
}

const q = (el, selector) => el.renderRoot.querySelector(selector);

afterEach(() => {
    document.body.innerHTML = '';
    document.cookie = 'pending_action=; path=/; max-age=0';
});

/** The `pending_action` cookie a signed-out click leaves behind. */
function pendingAction() {
    const match = document.cookie.match(/(?:^|; )pending_action=([^;]*)/);
    return match ? JSON.parse(decodeURIComponent(match[1])) : null;
}

describe('ol-shelf-button shapes', () => {
    test('split is the default: a main half and a menu half', async() => {
        const el = await mount({ userKey: '/people/tester' });
        stubFetch();
        expect(q(el, '.split')).not.toBeNull();
        expect(q(el, '.main').textContent.trim()).toBe('Want to Read');
        expect(q(el, '.more').getAttribute('aria-label')).toBe('More options for The Two Towers');
        expect(q(el, '.save')).toBeNull();
    });

    test('icon renders the bookmark and no main half', async() => {
        const el = await mount({ variant: 'icon', userKey: '/people/tester' });
        expect(q(el, '.save').getAttribute('aria-label')).toBe('Save The Two Towers to your reading log');
        expect(q(el, '.main')).toBeNull();
    });

    test('on a shelf, both shapes show it', async() => {
        const split = await mount({ shelf: SHELF.ALREADY_READ, userKey: '/people/tester' });
        expect(q(split, '.main').textContent.trim()).toBe('Already Read');
        expect(q(split, '.split').classList.contains('split--on')).toBe(true);

        const icon = await mount({ variant: 'icon', shelf: SHELF.CURRENTLY_READING, userKey: '/people/tester' });
        expect(q(icon, '.save').classList.contains('save--on')).toBe(true);
        expect(q(icon, '.save').getAttribute('aria-label')).toBe('The Two Towers is on your reading log');
        expect(q(icon, 'ol-icon').hasAttribute('filled')).toBe(true);
    });

    test('labels override the shelf names', async() => {
        const el = await mount({ userKey: '/people/tester', labels: { wantToRead: 'À lire' } });
        expect(q(el, '.main').textContent.trim()).toBe('À lire');
    });
});

describe('ol-shelf-button popover', () => {
    test('signed in, the trigger is wrapped in the actions popover with the book\'s state', async() => {
        const el = await mount({ shelf: SHELF.ALREADY_READ, rating: 4, userKey: '/people/tester' });
        const actions = q(el, 'ol-book-actions');
        expect(actions).not.toBeNull();
        expect(actions.shelf).toBe(SHELF.ALREADY_READ);
        expect(actions.rating).toBe(4);
        expect(actions.book).toEqual({ key: '/works/OL1W', title: 'The Two Towers', editionKey: 'OL1M' });
        expect(actions.querySelector('[slot="trigger"]')).not.toBeNull();
    });

    test('signed out, no popover is built at all', async() => {
        const el = await mount();
        expect(q(el, 'ol-book-actions')).toBeNull();
        expect(q(el, '.more')).not.toBeNull();
    });
});

describe('ol-shelf-button state changes', () => {
    test('clicking main adds to Want to Read and reports it before the request lands', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        const seen = [];
        el.addEventListener('ol-book-state-change', e => seen.push(e.detail));

        q(el, '.main').click();
        // Reported optimistically, on the same tick as the click.
        expect(seen).toEqual([{ key: '/works/OL1W', shelf: SHELF.WANT_TO_READ, rating: null }]);

        await new Promise(r => setTimeout(r, 0));
        const post = fetchCalls.find(c => c.url.endsWith('/works/OL1W/bookshelves.json'));
        expect(post.init.method).toBe('POST');
        expect(post.init.body.get('bookshelf_id')).toBe(String(SHELF.WANT_TO_READ));
        expect(post.init.body.get('edition_id')).toBe('OL1M');
    });

    test('clicking main while on a shelf removes it', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.ALREADY_READ, rating: 5, userKey: '/people/tester' });
        const seen = [];
        el.addEventListener('ol-book-state-change', e => seen.push(e.detail));

        q(el, '.main').click();
        expect(seen).toEqual([{ key: '/works/OL1W', shelf: null, rating: 5 }]);

        await new Promise(r => setTimeout(r, 0));
        // The removal is a POST against the shelf the book is already on.
        const post = fetchCalls.find(c => c.url.endsWith('/works/OL1W/bookshelves.json'));
        expect(post.init.body.get('bookshelf_id')).toBe(String(SHELF.ALREADY_READ));
    });

    test('never writes its own shelf — the surface owns it', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        // No listener applied the change, so the button still shows the old state.
        expect(el.shelf).toBeNull();
        expect(q(el, '.main').textContent.trim()).toBe('Want to Read');
    });

    test('a failed write is reported back so the surface can roll its state back', async() => {
        stubFetch({ ok: false, status: 500 });
        const el = await mount({ userKey: '/people/tester' });
        const seen = [];
        el.addEventListener('ol-book-state-change', e => seen.push(e.detail));

        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));

        expect(seen).toEqual([
            { key: '/works/OL1W', shelf: SHELF.WANT_TO_READ, rating: null },
            { key: '/works/OL1W', shelf: null, rating: null },
        ]);
    });

    test('the event crosses a shadow boundary so a composing parent hears it', async() => {
        stubFetch();
        const host = document.createElement('div');
        document.body.appendChild(host);
        const root = host.attachShadow({ mode: 'open' });
        const el = document.createElement('ol-shelf-button');
        Object.assign(el, { workKey: '/works/OL2W', shelf: null, userKey: '/people/tester' });
        root.appendChild(el);
        await el.updateComplete;

        const seen = [];
        document.addEventListener('ol-book-state-change', e => seen.push(e.detail.key));
        q(el, '.main').click();
        expect(seen).toEqual(['/works/OL2W']);
    });
});

describe('ol-shelf-button signed out', () => {
    // jsdom refuses the navigation redirectToLogin performs, so what is
    // asserted here is the part that has to survive it: the click is cancelled
    // and the intent is remembered.
    test('clicking main cancels the click and remembers the book', async() => {
        const el = await mount();
        const event = new MouseEvent('click', { bubbles: true, cancelable: true });
        q(el, '.main').dispatchEvent(event);
        expect(event.defaultPrevented).toBe(true);
        expect(pendingAction()).toEqual({
            name: 'The Two Towers', url: '/works/OL1W', action: 'Want to Read', type: 'book',
        });
    });

    test('clicking the menu half remembers it too, rather than opening nothing', async() => {
        const el = await mount();
        const event = new MouseEvent('click', { bubbles: true, cancelable: true });
        q(el, '.more').dispatchEvent(event);
        expect(event.defaultPrevented).toBe(true);
        expect(pendingAction().url).toBe('/works/OL1W');
    });

    test('no write is attempted', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));
        expect(fetchCalls).toHaveLength(0);
    });
});
