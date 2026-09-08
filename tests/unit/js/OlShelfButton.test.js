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

    test('outline is the icon shape in a bordered square: same trigger, same glyph', async() => {
        const el = await mount({ variant: 'outline', userKey: '/people/tester' });
        expect(el.getAttribute('variant')).toBe('outline');
        expect(q(el, '.save').getAttribute('aria-label')).toBe('Save The Two Towers to your reading log');
        expect(q(el, 'ol-icon').getAttribute('name')).toBe('bookmark');
        expect(q(el, '.main')).toBeNull();
        el.shelf = SHELF.ALREADY_READ;
        await el.updateComplete;
        expect(q(el, '.save').classList.contains('save--on')).toBe(true);
        expect(q(el, 'ol-icon').getAttribute('name')).toBe('circle-check-filled');
    });

    test('on a shelf, both shapes show it', async() => {
        const split = await mount({ shelf: SHELF.ALREADY_READ, userKey: '/people/tester' });
        expect(q(split, '.main').textContent.trim()).toBe('Already Read');
        expect(q(split, '.split').classList.contains('split--on')).toBe(true);

        const icon = await mount({ variant: 'icon', shelf: SHELF.CURRENTLY_READING, userKey: '/people/tester' });
        expect(q(icon, '.save').classList.contains('save--on')).toBe(true);
        expect(q(icon, '.save').getAttribute('aria-label')).toBe('The Two Towers is on your reading log');
    });

    test('the icon shape draws the shelf\'s glyph once shelved', async() => {
        const off = await mount({ variant: 'icon' });
        expect(q(off, 'ol-icon').getAttribute('name')).toBe('bookmark');

        // Shelved: the shelf's own glyph, as a solid shape.
        const wanted = await mount({ variant: 'icon', shelf: SHELF.WANT_TO_READ });
        expect(q(wanted, 'ol-icon').getAttribute('name')).toBe('bookmark-filled');
        const reading = await mount({ variant: 'icon', shelf: SHELF.CURRENTLY_READING });
        expect(q(reading, 'ol-icon').getAttribute('name')).toBe('book-open-filled');
        const read = await mount({ variant: 'icon', shelf: SHELF.ALREADY_READ });
        expect(q(read, 'ol-icon').getAttribute('name')).toBe('circle-check-filled');
        const stopped = await mount({ variant: 'icon', shelf: SHELF.STOPPED_READING });
        expect(q(stopped, 'ol-icon').getAttribute('name')).toBe('circle-pause-filled');
    });

    test('a glyph change keeps the old one as an outgoing layer until its animation ends', async() => {
        const el = await mount({ variant: 'icon' });
        // First paint: nothing to hand over from.
        expect(el.shadowRoot.querySelectorAll('ol-icon').length).toBe(1);

        el.shelf = SHELF.ALREADY_READ;
        await el.updateComplete;
        const glyphs = el.shadowRoot.querySelectorAll('ol-icon');
        expect([...glyphs].map((g) => g.getAttribute('name'))).toEqual(['circle-check-filled', 'bookmark']);
        expect(glyphs[0].classList.contains('glyph--in')).toBe(true);
        expect(glyphs[1].classList.contains('glyph--out')).toBe(true);

        glyphs[1].dispatchEvent(new Event('animationend'));
        await el.updateComplete;
        expect(el.shadowRoot.querySelectorAll('ol-icon').length).toBe(1);
        expect(q(el, 'ol-icon').classList.contains('glyph--in')).toBe(false);

        // A change mid-swap hands over from the glyph that was showing, not the one already leaving.
        el.shelf = SHELF.STOPPED_READING;
        await el.updateComplete;
        el.shelf = null;
        await el.updateComplete;
        expect([...el.shadowRoot.querySelectorAll('ol-icon')].map((g) => g.getAttribute('name'))).toEqual(['bookmark', 'circle-pause-filled']);
    });

    test('reflects the shelf, so the page\'s CSS can tell a saved book apart', async() => {
        const el = await mount({ shelf: SHELF.WANT_TO_READ });
        expect(el.getAttribute('shelf')).toBe('1');
        el.shelf = null;
        await el.updateComplete;
        expect(el.hasAttribute('shelf')).toBe(false);
    });

    test('labels override the shelf names', async() => {
        const el = await mount({ userKey: '/people/tester', labels: { wantToRead: 'À lire' } });
        expect(q(el, '.main').textContent.trim()).toBe('À lire');
    });
});

describe('ol-shelf-button popover', () => {
    test('signed in, the trigger is wrapped in the actions popover with the book\'s state', async() => {
        const el = await mount({ shelf: SHELF.ALREADY_READ, rating: 4, userKey: '/people/tester' });
        const actions = q(el, 'ol-shelf-actions');
        expect(actions).not.toBeNull();
        expect(actions.shelf).toBe(SHELF.ALREADY_READ);
        expect(actions.rating).toBe(4);
        expect(actions.book).toEqual({ key: '/works/OL1W', title: 'The Two Towers', editionKey: 'OL1M' });
        expect(actions.querySelector('[slot="trigger"]')).not.toBeNull();
    });

    test('carries `open` on the host while the popover is open', async() => {
        const el = await mount({ userKey: '/people/tester' });
        const actions = q(el, 'ol-shelf-actions');
        expect(el.hasAttribute('open')).toBe(false);
        actions.shadowRoot.querySelector('ol-popover').open = true;
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(el.hasAttribute('open')).toBe(true);
        // A close the panel cancels (Escape stepping back a pane) is not a close.
        const kept = new CustomEvent('ol-popover-close', { bubbles: true, composed: true, cancelable: true });
        kept.preventDefault();
        actions.dispatchEvent(kept);
        expect(el.hasAttribute('open')).toBe(true);
        actions.dispatchEvent(new CustomEvent('ol-popover-close', { bubbles: true, composed: true, cancelable: true }));
        expect(el.hasAttribute('open')).toBe(false);
    });

    test('signed out, no popover is built at all', async() => {
        const el = await mount();
        expect(q(el, 'ol-shelf-actions')).toBeNull();
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

    test('a second click before the request lands is dropped', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        const seen = [];
        el.addEventListener('ol-book-state-change', e => seen.push(e.detail));

        q(el, '.main').click();
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));

        // The surface has not applied the first change yet, so without the
        // guard the second click would post the same toggle again.
        expect(seen).toEqual([{ key: '/works/OL1W', shelf: SHELF.WANT_TO_READ, rating: null }]);
        expect(fetchCalls.filter(c => c.url.endsWith('/works/OL1W/bookshelves.json'))).toHaveLength(1);
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
            // The resume target is the page they were on — jsdom's '/' here.
            // On a list of results the book's own page would strand them
            // somewhere they never asked to go.
            name: 'The Two Towers', url: '/', action: 'Want to Read', type: 'book',
        });
    });

    test('clicking the menu half remembers it too, rather than opening nothing', async() => {
        const el = await mount();
        const event = new MouseEvent('click', { bubbles: true, cancelable: true });
        q(el, '.more').dispatchEvent(event);
        expect(event.defaultPrevented).toBe(true);
        expect(pendingAction().name).toBe('The Two Towers');
    });

    test('no write is attempted', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));
        expect(fetchCalls).toHaveLength(0);
    });
});

describe('ol-shelf-button pass-through to the popover', () => {
    test('hands hide-rating to ol-shelf-actions', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester', hideRating: true });
        expect(q(el, 'ol-shelf-actions').hideRating).toBe(true);
    });

    test('it defaults to off', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        expect(q(el, 'ol-shelf-actions').hideRating).toBe(false);
    });

    test('hands pending to ol-shelf-actions, and reflects it', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester', pending: true });
        expect(q(el, 'ol-shelf-actions').pending).toBe(true);
        expect(el.hasAttribute('pending')).toBe(true);
    });
});

describe('ol-shelf-button pending', () => {
    // The main half toggles: with the shelf unknown it would be guessing, and
    // a wrong guess posts the shelf the book is on, which removes it.
    test('the main half does nothing until the state is known', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester', pending: true });
        const seen = [];
        el.addEventListener('ol-book-state-change', e => seen.push(e.detail));
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));
        expect(seen).toEqual([]);
        expect(fetchCalls).toHaveLength(0);

        el.pending = false;
        await el.updateComplete;
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));
        expect(seen).toHaveLength(1);
    });

    test('looks unshelved rather than guessing', async() => {
        const el = await mount({ variant: 'outline', userKey: '/people/tester', pending: true });
        expect(q(el, '.save').classList.contains('save--on')).toBe(false);
        expect(q(el, 'ol-icon').getAttribute('name')).toBe('bookmark');
    });
});

describe('ol-shelf-button accessible name and state', () => {
    test('the main half names the book and reports pressed', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        const main = q(el, '.main');
        expect(main.getAttribute('aria-label')).toBe('Want to Read: The Two Towers');
        expect(main.getAttribute('aria-pressed')).toBe('false');
        el.shelf = SHELF.CURRENTLY_READING;
        await el.updateComplete;
        expect(main.getAttribute('aria-label')).toBe('Currently Reading: The Two Towers');
        expect(main.getAttribute('aria-pressed')).toBe('true');
    });

    test('a main click is announced, on and off', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        const live = q(el, '.sr-only');
        expect(live.getAttribute('role')).toBe('status');
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(live.textContent).toBe('Added to Want to Read');
        el.shelf = SHELF.WANT_TO_READ;
        await el.updateComplete;
        q(el, '.main').click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(live.textContent).toBe('Removed from shelf');
    });

    test('translated labels reach the name', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester', labels: { wantToRead: 'À lire', shelfToggle: '%(title)s — %(shelf)s' } });
        expect(q(el, '.main').getAttribute('aria-label')).toBe('The Two Towers — À lire');
    });
});
