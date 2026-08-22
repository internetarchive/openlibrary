/**
 * Unit tests for <ol-book-actions>: shelf/rating requests and their optimistic
 * updates, the state-change event, and the add-to-list pane (load, filter,
 * toggle, create). Network is stubbed at `fetch`.
 */
import { OlBookActions, resetListsCache, fmt } from '../../../openlibrary/components/lit/OlBookActions.js';
import { SHELF } from '../../../openlibrary/components/lit/utils/books-api.js';

const BOOK = { key: '/works/OL1W', title: 'Project Hail Mary', firstPublishYear: 2021, editionKey: 'OL9M' };

let calls;
let listData;

function stubFetch({ failWith } = {}) {
    calls = [];
    listData = {
        '/people/tester/lists/OL1L': { listName: 'Summer 2026', members: ['/works/OL7W'] },
        '/people/tester/lists/OL2L': { listName: 'Sci-fi to reread', members: ['/works/OL1W'] },
    };
    global.fetch = jest.fn(async(url, init) => {
        calls.push({ url, init });
        if (failWith) return { ok: false, status: failWith, json: async() => ({}) };
        let body = {};
        if (url.endsWith('/partials/MyBooksDropperLists.json')) body = { dropper: '', listData };
        if (url.endsWith('/lists.json') && init?.method === 'POST') body = { key: '/people/tester/lists/OL3L', revision: 1 };
        return { ok: true, status: 200, json: async() => body };
    });
}

beforeAll(() => {
    global.ResizeObserver = class { observe() {} disconnect() {} };
    window.matchMedia = query => ({
        matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    });
});

beforeEach(() => {
    resetListsCache();
});

afterEach(() => {
    document.body.innerHTML = '';
});

async function tick(el) {
    await new Promise(r => setTimeout(r, 0));
    await el.updateComplete;
}

async function mount(props = {}) {
    const el = new OlBookActions();
    el.book = BOOK;
    el.userKey = '/people/tester';
    Object.assign(el, props);
    const trigger = document.createElement('button');
    trigger.slot = 'trigger';
    el.appendChild(trigger);
    document.body.appendChild(el);
    await el.updateComplete;
    // Open the popover so the panel exists.
    el.shadowRoot.querySelector('ol-popover').open = true;
    await tick(el);
    return el;
}

const q = (el, sel) => el.shadowRoot.querySelector(sel);
const qa = (el, sel) => [...el.shadowRoot.querySelectorAll(sel)];

describe('fmt', () => {
    test('interpolates %(name)s placeholders', () => {
        expect(fmt('by %(name)s', { name: 'Andy' })).toBe('by Andy');
        expect(fmt('%(count)s items', { count: 3 })).toBe('3 items');
    });
});

describe('ol-book-actions shelves', () => {
    test('renders header and four shelf rows with the current one checked', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.CURRENTLY_READING });
        expect(q(el, '.header').textContent.replace(/\s+/g, ' ').trim()).toBe('Project Hail Mary (2021)');
        const rows = qa(el, '.row[role="menuitemradio"]');
        expect(rows.map(r => r.getAttribute('aria-checked'))).toEqual(['false', 'true', 'false', 'false']);
    });

    test('clicking a shelf posts it, updates optimistically, and emits state', async() => {
        stubFetch();
        const el = await mount();
        const events = [];
        el.addEventListener('ol-book-state-change', e => events.push(e.detail));
        qa(el, '.row[role="menuitemradio"]')[0].click();
        expect(el.shelf).toBe(SHELF.WANT_TO_READ);
        await tick(el);
        const post = calls.find(c => c.url === '/works/OL1W/bookshelves.json');
        expect(post.init.method).toBe('POST');
        expect(post.init.body.get('bookshelf_id')).toBe('1');
        expect(post.init.body.get('edition_id')).toBe('OL9M');
        expect(events).toEqual([{ key: '/works/OL1W', shelf: SHELF.WANT_TO_READ, rating: null }]);
    });

    test('clicking the current shelf removes it', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.WANT_TO_READ });
        qa(el, '.row[role="menuitemradio"]')[0].click();
        expect(el.shelf).toBeNull();
        await tick(el);
        // Server toggles off when it receives the current shelf id.
        expect(calls.find(c => c.url === '/works/OL1W/bookshelves.json').init.body.get('bookshelf_id')).toBe('1');
    });

    test('rolls back and toasts on failure', async() => {
        stubFetch({ failWith: 500 });
        const el = await mount();
        qa(el, '.row[role="menuitemradio"]')[2].click();
        expect(el.shelf).toBe(SHELF.ALREADY_READ);
        await tick(el);
        expect(el.shelf).toBeNull();
        expect(document.querySelector('ol-toast')).not.toBeNull();
    });
});

describe('ol-book-actions rating', () => {
    test('rating posts and moves the book to Already Read', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.star')[3].click();
        expect(el.rating).toBe(4);
        expect(el.shelf).toBe(SHELF.ALREADY_READ);
        await tick(el);
        const post = calls.find(c => c.url === '/works/OL1W/ratings.json');
        expect(post.init.body.get('rating')).toBe('4');
        expect(q(el, '.stars .caption').textContent).toBe('Clear rating');
    });

    test('clicking the current star clears the rating', async() => {
        stubFetch();
        const el = await mount({ rating: 2, shelf: SHELF.ALREADY_READ });
        qa(el, '.star')[1].click();
        expect(el.rating).toBeNull();
        await tick(el);
        expect(calls.find(c => c.url === '/works/OL1W/ratings.json').init.body.has('rating')).toBe(false);
    });
});

describe('ol-book-actions lists pane', () => {
    test('opening the popover prefetches lists so the count shows straight away', async() => {
        stubFetch();
        const el = await mount();
        await tick(el);
        expect(calls.some(c => c.url.endsWith('/partials/MyBooksDropperLists.json'))).toBe(true);
        // The stub puts OL1W in one of the two lists.
        expect(q(el, '.group:last-child .count').textContent).toBe('1');
    });

    test('a failed prefetch stays silent and lets the pane retry', async() => {
        stubFetch({ failWith: 500 });
        const el = await mount();
        await tick(el);
        expect(el._lists).toBeNull();
        expect(q(el, '.group:last-child .count')).toBeNull();
    });

    test('opens the pane, loads lists with membership and counts', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.group:last-child .row').click();
        await tick(el);
        expect(el._pane).toBe('lists');
        expect(q(el, '.track').classList.contains('pane-lists')).toBe(true);
        expect(calls.some(c => c.url.endsWith('/partials/MyBooksDropperLists.json'))).toBe(true);
        const rows = qa(el, '.list-row');
        expect(rows.map(r => r.querySelector('.name').textContent)).toEqual(['Summer 2026', 'Sci-fi to reread']);
        expect(rows.map(r => r.querySelector('input').checked)).toEqual([false, true]);
        expect(rows.map(r => r.querySelector('.count').textContent)).toEqual(['1', '1']);
    });

    test('filter narrows the rows', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.group:last-child .row').click();
        await tick(el);
        const input = q(el, '.pane:nth-child(2) .input');
        input.value = 'sci';
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
        expect(qa(el, '.list-row')).toHaveLength(1);
        input.value = 'zzz';
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
        expect(q(el, '.empty').textContent).toBe('No lists match.');
    });

    test('toggling a checkbox adds/removes the seed', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.group:last-child .row').click();
        await tick(el);
        const [first, second] = qa(el, '.list-row input');
        first.checked = true;
        first.dispatchEvent(new Event('change'));
        second.checked = false;
        second.dispatchEvent(new Event('change'));
        await tick(el);
        const add = calls.find(c => c.url === '/people/tester/lists/OL1L/seeds.json');
        const remove = calls.find(c => c.url === '/people/tester/lists/OL2L/seeds.json');
        expect(JSON.parse(add.init.body)).toEqual({ add: [{ key: '/works/OL1W' }] });
        expect(JSON.parse(remove.init.body)).toEqual({ remove: [{ key: '/works/OL1W' }] });
        expect(qa(el, '.list-row .count').map(c => c.textContent)).toEqual(['2', '0']);
    });

    test('create list inlines an input, posts, and prepends the new list', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.group:last-child .row').click();
        await tick(el);
        q(el, '.lists-header ol-button').click();
        await el.updateComplete;
        const form = q(el, 'form.field');
        expect(form).not.toBeNull();
        form.querySelector('input').value = 'Gothic autumn';
        form.dispatchEvent(new Event('submit', { cancelable: true }));
        await tick(el);
        const post = calls.find(c => c.url === '/people/tester/lists.json');
        expect(JSON.parse(post.init.body)).toEqual({ name: 'Gothic autumn', description: '', seeds: [{ key: '/works/OL1W' }] });
        expect(el._creating).toBe(false);
        const rows = qa(el, '.list-row');
        expect(rows[0].querySelector('.name').textContent).toBe('Gothic autumn');
        expect(rows[0].querySelector('input').checked).toBe(true);
    });

    test('Escape in the lists pane goes back instead of closing', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.group:last-child .row').click();
        await tick(el);
        const popover = q(el, 'ol-popover');
        popover._requestClose('escape');
        await tick(el);
        expect(popover.open).toBe(true);
        expect(el._pane).toBe('main');
        popover._requestClose('escape');
        await tick(el);
        expect(popover.open).toBe(false);
    });
});

describe('ol-book-actions hide-rating', () => {
    test('drops the stars but keeps shelves and lists', async() => {
        stubFetch();
        const el = await mount({ hideRating: true });
        expect(q(el, '.group.rating')).toBeNull();
        expect(qa(el, '.group.shelves .row')).toHaveLength(4);
        expect(q(el, '.group.lists-entry')).not.toBeNull();
    });

    test('renders the stars by default', async() => {
        stubFetch();
        const el = await mount();
        expect(q(el, '.group.rating')).not.toBeNull();
    });
});

describe('ol-book-actions rejected writes', () => {
    // bookshelves.json answers a rejected write with 200 and an `error` key,
    // so a status-only check would let the optimistic update stand.
    test('a 200 carrying `error` rolls the shelf back', async() => {
        stubFetch();
        global.fetch = jest.fn(async(url, init) => {
            calls.push({ url, init });
            return { ok: true, status: 200, json: async() => ({ error: 'Invalid bookshelf' }) };
        });
        const el = await mount();
        qa(el, '.group.shelves .row')[0].click();
        await tick(el);
        expect(el.shelf).toBeNull();
    });
});
