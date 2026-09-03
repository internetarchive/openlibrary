/**
 * Unit tests for <ol-shelf-actions>: shelf/rating requests and their optimistic
 * updates, the state-change event, and the add-to-list pane (load, filter,
 * toggle, create, and the recently-used lists it leans on). Network is stubbed
 * at `fetch`.
 */
import { OlShelfActions } from '../../../openlibrary/components/lit/OlShelfActions.js';
import { fmt } from '../../../openlibrary/components/lit/utils/labels.js';
import { SHELF } from '../../../openlibrary/components/lit/utils/books-api.js';
import { quickYears } from '../../../openlibrary/components/lit/utils/dates.js';
import { getLists, resetListsStore } from '../../../openlibrary/components/lit/utils/lists-store.js';
import { clearRecentLists, getRecentLists, noteListUsed } from '../../../openlibrary/components/lit/utils/recent-lists.js';

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
        if (url.includes('/check-ins')) body = { status: 'ok', id: 42 };
        return { ok: true, status: 200, json: async() => body };
    });
}

/** Pads the stub past FILTER_THRESHOLD, the count at which the pane offers a filter. */
function padLists(n = 7) {
    for (let i = 0; i < n; i++) listData[`/people/tester/lists/OL1${i}L`] = { listName: `Filler ${i}`, members: [] };
}

beforeAll(() => {
    global.ResizeObserver = class { observe() {} disconnect() {} };
    window.matchMedia = query => ({
        matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    });
});

beforeEach(() => {
    resetListsStore();
    clearRecentLists();
});

afterEach(() => {
    document.body.innerHTML = '';
});

async function tick(el) {
    await new Promise(r => setTimeout(r, 0));
    await el.updateComplete;
}

async function mount(props = {}) {
    const el = new OlShelfActions();
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

describe('ol-shelf-actions shelves', () => {
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

    // Clicking the shelf you are on is the way off it, so the link would be a
    // second way of doing the same thing — except on Already Read, whose row
    // goes to the date pane instead.
    test('only Already Read offers a Remove from shelf link', async() => {
        stubFetch();
        for (const shelf of [null, SHELF.WANT_TO_READ, SHELF.CURRENTLY_READING, SHELF.STOPPED_READING]) {
            expect(q(await mount({ shelf }), '.clear-shelf')).toBeNull();
        }
        expect(q(await mount({ shelf: SHELF.ALREADY_READ }), '.clear-shelf')).not.toBeNull();
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

describe('ol-shelf-actions rating', () => {
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

describe('ol-shelf-actions lists pane', () => {
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
        expect(getLists()).toBeNull();
        expect(q(el, '.group:last-child .count')).toBeNull();
    });

    test('opens the pane, loads lists with membership and counts', async() => {
        stubFetch();
        const el = await mount();
        q(el, '.group:last-child .row').click();
        await tick(el);
        expect(el._pane).toBe('lists');
        // The track is translated by one panel width per pane index, so the
        // slide is derived rather than a per-pane class.
        expect(q(el, '.track').style.transform).toMatch(/^translateX\(-33\.3/);
        expect(calls.some(c => c.url.endsWith('/partials/MyBooksDropperLists.json'))).toBe(true);
        const rows = qa(el, '.list-row');
        expect(rows.map(r => r.querySelector('.name').textContent)).toEqual(['Summer 2026', 'Sci-fi to reread']);
        expect(rows.map(r => r.querySelector('input').checked)).toEqual([false, true]);
        expect(rows.map(r => r.querySelector('.count').textContent)).toEqual(['1', '1']);
    });

    test('filter narrows the rows', async() => {
        stubFetch();
        padLists();
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

describe('ol-shelf-actions lists pane, sized to the reader', () => {
    const openPane = async(el) => {
        el.shadowRoot.querySelector('.group:last-child .row').click();
        await tick(el);
    };

    test('offers no filter until there are enough lists to need one', async() => {
        stubFetch();
        const el = await mount();
        await openPane(el);
        expect(q(el, '.pane:nth-child(2) .input')).toBeNull();
        // Focus lands on the first list instead, so the pane is still workable
        // from the keyboard.
        expect(el.shadowRoot.activeElement).toBe(qa(el, '.list-row input')[0]);
    });

    test('offers one once the lists stop being scannable', async() => {
        stubFetch();
        padLists();
        const el = await mount();
        await openPane(el);
        const input = q(el, '.pane:nth-child(2) .input');
        expect(input.getAttribute('aria-label')).toBe('Filter lists…');
        expect(el.shadowRoot.activeElement).toBe(input);
    });

    test('with no lists yet, the pane is the create form', async() => {
        stubFetch();
        listData = {};
        const el = await mount();
        await openPane(el);
        expect(q(el, '.pane:nth-child(2) .caption').textContent).toBe('Create your first list');
        const form = q(el, 'form.field');
        expect(form.querySelector('.input').getAttribute('aria-label')).toBe('List name');
        expect(el.shadowRoot.activeElement).toBe(form.querySelector('.input'));
        // Nothing else competing: no filter, no rows, and no second way in.
        expect(qa(el, '.list-row')).toHaveLength(0);
        expect(q(el, '.lists-header ol-button')).toBeNull();
    });

    test('the first list drops the create form and leaves a row', async() => {
        stubFetch();
        listData = {};
        const el = await mount();
        await openPane(el);
        const form = q(el, 'form.field');
        form.querySelector('input').value = 'Gothic autumn';
        form.dispatchEvent(new Event('submit', { cancelable: true }));
        await tick(el);
        expect(q(el, '.pane:nth-child(2) .caption')).toBeNull();
        expect(q(el, 'form.field')).toBeNull();
        expect(qa(el, '.list-row .name').map(n => n.textContent)).toEqual(['Gothic autumn']);
    });

    test('Escape out of that form leaves the pane, not the form', async() => {
        stubFetch();
        listData = {};
        const el = await mount();
        await openPane(el);
        q(el, 'form.field .input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await tick(el);
        expect(el._pane).toBe('main');
        expect(q(el, 'ol-popover').open).toBe(true);
    });
});

describe('ol-shelf-actions shared lists', () => {
    async function createList(el, name) {
        q(el, '.group:last-child .row').click();
        await tick(el);
        q(el, '.lists-header ol-button').click();
        await el.updateComplete;
        const form = q(el, 'form.field');
        form.querySelector('input').value = name;
        form.dispatchEvent(new Event('submit', { cancelable: true }));
        await tick(el);
    }

    test('creating a list announces it with ol-list-created', async() => {
        stubFetch();
        const el = await mount();
        const seen = [];
        document.addEventListener('ol-list-created', e => seen.push(e), { once: true });
        await createList(el, 'Gothic autumn');
        expect(seen).toHaveLength(1);
        expect(seen[0].detail).toEqual({ key: '/people/tester/lists/OL3L', name: 'Gothic autumn', seedKey: '/works/OL1W' });
    });

    test('a sibling popover picks up the new list without refetching', async() => {
        stubFetch();
        const el = await mount();
        const sibling = await mount({ book: { ...BOOK, key: '/works/OL2W' } });
        await tick(sibling);
        const fetches = () => calls.filter(c => c.url.endsWith('/partials/MyBooksDropperLists.json')).length;
        const before = fetches();
        await createList(el, 'Gothic autumn');
        // The sibling reads the shared store, so the new list is already there.
        sibling.shadowRoot.querySelector('.group:last-child .row').click();
        await tick(sibling);
        const firstRow = qa(sibling, '.list-row')[0];
        expect(firstRow.querySelector('.name').textContent).toBe('Gothic autumn');
        // Unchecked for the sibling: only the creator's seed is on the list.
        expect(firstRow.querySelector('input').checked).toBe(false);
        expect(fetches()).toBe(before);
    });

});

describe('recent lists store', () => {
    test('keeps the lists per user, most recent first, three at most', () => {
        ['/l/1', '/l/2', '/l/3', '/l/4'].forEach((key, i) => noteListUsed('/people/a', key, `L${i + 1}`));
        noteListUsed('/people/b', '/l/9', 'Theirs');
        expect(getRecentLists('/people/a').map(r => r.key)).toEqual(['/l/4', '/l/3', '/l/2']);
        expect(getRecentLists('/people/b')).toEqual([{ key: '/l/9', name: 'Theirs' }]);
    });

    test('using a list again moves it up rather than repeating it', () => {
        noteListUsed('/people/a', '/l/1', 'One');
        noteListUsed('/people/a', '/l/2', 'Two');
        noteListUsed('/people/a', '/l/1', 'One');
        expect(getRecentLists('/people/a').map(r => r.key)).toEqual(['/l/1', '/l/2']);
    });

    test('forgets lists last used too long ago to still be a session', () => {
        const stale = Date.now() - 30 * 24 * 60 * 60 * 1000;
        window.localStorage.setItem('ol.recentLists', JSON.stringify({ '/people/a': [{ key: '/l/1', name: 'Old', ts: stale }] }));
        expect(getRecentLists('/people/a')).toEqual([]);
    });
});

describe('ol-shelf-actions recent lists', () => {
    const openPane = async(el) => {
        el.shadowRoot.querySelector('.group:last-child .row').click();
        await tick(el);
    };

    const names = (el, sel = '.list-row .name') => qa(el, sel).map(n => n.textContent);

    async function reopen(el) {
        const popover = q(el, 'ol-popover');
        popover.open = false;
        await tick(el);
        popover.open = true;
        await tick(el);
    }

    async function toggle(el, index, checked) {
        const input = qa(el, '.list-row input')[index];
        input.checked = checked;
        input.dispatchEvent(new Event('change'));
        await tick(el);
    }

    test('a used list moves to the front of the store, but never under the open pane', async() => {
        stubFetch();
        const el = await mount();
        await openPane(el);
        await toggle(el, 1, false);
        // The store matches what a reload would show — the server sorts by
        // last_modified, and the write we just made bumped it.
        expect(Object.keys(getLists())[0]).toBe('/people/tester/lists/OL2L');
        // The pane keeps the order it opened with, so no row moves mid-session.
        expect(names(el)).toEqual(['Summer 2026', 'Sci-fi to reread']);
        await reopen(el);
        await openPane(el);
        expect(names(el)).toEqual(['Sci-fi to reread', 'Summer 2026']);
    });

    test('the next book offers the last list used, one tap away', async() => {
        stubFetch();
        const el = await mount();
        await openPane(el);
        await toggle(el, 0, true);

        const next = await mount({ book: { ...BOOK, key: '/works/OL2W' } });
        await tick(next);
        const shortcut = q(next, '.row.shortcut');
        expect(shortcut.querySelector('.label').textContent).toBe('Summer 2026');
        expect(shortcut.getAttribute('aria-checked')).toBe('false');

        shortcut.click();
        await tick(next);
        const post = calls.filter(c => c.url === '/people/tester/lists/OL1L/seeds.json').pop();
        expect(JSON.parse(post.init.body)).toEqual({ add: [{ key: '/works/OL2W' }] });
        expect(q(next, '.row.shortcut').getAttribute('aria-checked')).toBe('true');
    });

    test('the shortcut renders from the remembered name, so the panel never grows a row mid-open', async() => {
        noteListUsed('/people/tester', '/people/tester/lists/OL1L', 'Summer 2026');
        stubFetch();
        global.fetch = jest.fn(() => new Promise(() => {})); // lists never arrive
        const el = await mount();
        expect(getLists()).toBeNull();
        expect(q(el, '.row.shortcut .label').textContent).toBe('Summer 2026');
    });

    test('a remembered list that has since gone takes its row with it', async() => {
        noteListUsed('/people/tester', '/people/tester/lists/OL9L', 'Deleted');
        stubFetch();
        const el = await mount();
        await tick(el);
        expect(q(el, '.row.shortcut')).toBeNull();
    });

    test('pins the recent lists above the rest once there are enough to scroll', async() => {
        stubFetch();
        [3, 4, 5, 6].forEach(n => { listData[`/people/tester/lists/OL${n}L`] = { listName: `List ${n}`, members: [] }; });
        noteListUsed('/people/tester', '/people/tester/lists/OL5L', 'List 5');
        const el = await mount();
        await openPane(el);
        const groups = qa(el, '.group-lists');
        expect(groups.map(g => g.getAttribute('aria-label'))).toEqual(['Recently used', 'Other lists']);
        expect([...groups[0].querySelectorAll('.name')].map(n => n.textContent)).toEqual(['List 5']);
        // Pinned rows are hoisted, not copied.
        expect([...groups[1].querySelectorAll('.name')].map(n => n.textContent)).not.toContain('List 5');
    });

    test('leaves a short list of lists alone', async() => {
        noteListUsed('/people/tester', '/people/tester/lists/OL2L', 'Sci-fi to reread');
        stubFetch();
        const el = await mount();
        await openPane(el);
        expect(qa(el, '.group-lists')).toHaveLength(0);
        expect(q(el, '.pane:nth-child(2) .input')).toBeNull();
        expect(names(el)).toEqual(['Summer 2026', 'Sci-fi to reread']);
    });

    test('Enter toggles the first filtered row and says which', async() => {
        stubFetch();
        padLists();
        const el = await mount();
        await openPane(el);
        const input = q(el, '.pane:nth-child(2) .input');
        // Nothing typed, nothing to commit to.
        expect(q(el, '.list-row.target')).toBeNull();

        input.value = 'summer';
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
        expect(q(el, '.list-row.target .name').textContent).toBe('Summer 2026');

        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', cancelable: true }));
        await tick(el);
        const post = calls.find(c => c.url === '/people/tester/lists/OL1L/seeds.json');
        expect(JSON.parse(post.init.body)).toEqual({ add: [{ key: '/works/OL1W' }] });
        expect(q(el, '.pane:nth-child(2) .sr-only').textContent).toBe('Added to Summer 2026');
        // The filter stays put: the row it matched is right there, now checked.
        expect(input.value).toBe('summer');
    });
});

describe('ol-shelf-actions hide-rating', () => {
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

describe('ol-shelf-actions rejected writes', () => {
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

    // A rating moves two properties, so rolling back the rating alone would
    // leave the book on a shelf it was never put on.
    test('a rejected rating rolls back the shelf it implied too', async() => {
        stubFetch({ failWith: 500 });
        const el = await mount({ shelf: SHELF.CURRENTLY_READING });
        qa(el, '.star')[3].click();
        expect(el.shelf).toBe(SHELF.ALREADY_READ);
        await tick(el);
        expect(el.rating).toBeNull();
        expect(el.shelf).toBe(SHELF.CURRENTLY_READING);
    });

    test('a second write while one is in flight is dropped', async() => {
        stubFetch();
        let land;
        global.fetch = jest.fn((url, init) => {
            calls.push({ url, init });
            return new Promise(resolve => { land = () => resolve({ ok: true, status: 200, json: async() => ({}) }); });
        });
        const el = await mount();

        // Both land before the re-render that disables the stars, so the guard
        // is what stops the second one.
        qa(el, '.star')[2].click();
        qa(el, '.star')[4].click();
        await tick(el);

        expect(calls.filter(c => c.url === '/works/OL1W/ratings.json')).toHaveLength(1);
        expect(el.rating).toBe(3);
        land();
    });
});

const checkInWrites = () => calls.filter(c => c.url.includes('/check-ins'));
const checkInPane = el => el.shadowRoot.querySelectorAll('.pane')[2];
const paneRows = el => [...checkInPane(el).querySelectorAll('.row')];
const yearRows = el => [...checkInPane(el).querySelectorAll('.row.year')];
const otherDateRow = el => checkInPane(el).querySelector('.row.date-toggle');
const clearDateLink = el => checkInPane(el).querySelector('.clear-date');

describe('quickYears', () => {
    test('one year once the new year has bedded in', () => {
        expect(quickYears(new Date(2026, 7, 22))).toEqual([2026]);
    });

    test('the year just gone stays on offer for the first 30 days', () => {
        expect(quickYears(new Date(2026, 0, 25))).toEqual([2026, 2025]);
        expect(quickYears(new Date(2026, 0, 1))).toEqual([2026, 2025]);
    });

    test('and drops off after them', () => {
        expect(quickYears(new Date(2026, 0, 31))).toEqual([2026]);
    });
});

describe('ol-shelf-actions check-in pane', () => {
    test('marking a book read slides the date question in', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        expect(el._pane).toBe('checkIn');
        expect(paneRows(el).map(r => r.textContent.trim())).toEqual([
            'Today', ...quickYears().map(y => `In ${y}`), 'Other date',
        ]);
    });

    test('the other three shelves do not', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[1].click();
        await tick(el);
        expect(el._pane).toBe('main');
    });

    test('a book already on the shelf opens the pane to amend its date', async() => {
        stubFetch();
        // What the row's chevron promises — and the only way to change a date
        // once given. Coming off the shelf is the main button's job.
        const el = await mount({ shelf: SHELF.ALREADY_READ });
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        expect(el._pane).toBe('checkIn');
        expect(calls.find(c => c.url === '/works/OL1W/bookshelves.json')).toBeUndefined();
    });

    test('rating a book does not, even though the server moves it to Already Read', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.star')[3].click();
        await tick(el);
        expect(el.shelf).toBe(SHELF.ALREADY_READ);
        expect(el._pane).toBe('main');
    });

    test('a failed shelf write asks nothing', async() => {
        stubFetch({ failWith: 500 });
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        expect(el._pane).toBe('main');
    });

    test('the date already given rides on the Already Read row', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.ALREADY_READ, readDate: '2026' });
        const row = qa(el, '.group.shelves .row')[2];
        expect(row.querySelector('.count').textContent).toBe('2026');
        // A chevron, not a check: the row leads to the date pane.
        expect(row.querySelector('.trail').getAttribute('name')).toBe('chevron-right');
    });

    test('a partial date shows only what is known', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.ALREADY_READ, readDate: '2026-08' });
        expect(qa(el, '.group.shelves .row')[2].querySelector('.count').textContent).toBe('Aug 2026');
    });

    // The server keeps check-ins through a shelf move (only coming off the
    // shelves deletes them), so the date outlives the shelf it was given on.
    test('but not once the book has moved to another shelf', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.CURRENTLY_READING, readDate: '2026' });
        const row = qa(el, '.group.shelves .row')[2];
        expect(row.querySelector('.count')).toBeNull();
        // Still a way through to the date, which the popover has not forgotten.
        expect(row.querySelector('.trail').getAttribute('name')).toBe('chevron-right');
        expect(el.readDate).toBe('2026');
    });

    test('amending a date edits the same check-in rather than adding one', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.ALREADY_READ, readDate: '2025', eventId: 12 });
        const events = [];
        el.addEventListener('ol-book-check-in', e => events.push(e.detail));
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        yearRows(el)[0].click();
        await tick(el);
        const body = JSON.parse(checkInWrites()[0].init.body);
        expect(body.event_id).toBe(12);
        expect(events).toEqual([{ key: '/works/OL1W', date: String(new Date().getFullYear()), eventId: 42 }]);
    });

    test('Today posts a full date', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        paneRows(el)[0].click();
        await tick(el);
        const now = new Date();
        expect(JSON.parse(checkInWrites()[0].init.body)).toEqual({
            event_type: 3,
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            day: now.getDate(),
            edition_key: 'OL9M',
            event_id: null,
        });
        expect(el._pane).toBe('main');
    });

    test('this year posts a year on its own', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        yearRows(el)[0].click();
        await tick(el);
        const body = JSON.parse(checkInWrites()[0].init.body);
        expect(body.year).toBe(new Date().getFullYear());
        expect(body.month).toBeNull();
        expect(body.day).toBeNull();
    });

    test('other date reveals the selects, month and day gated in turn', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        otherDateRow(el).click();
        await tick(el);

        const selects = () => [...checkInPane(el).querySelectorAll('.select')];
        expect(selects()).toHaveLength(3);
        // Disclosed under the row, not in place of it: the one-tap answers
        // stay on screen.
        expect(paneRows(el)).toHaveLength(2 + yearRows(el).length);
        expect(selects()[1].disabled).toBe(true);
        expect(selects()[2].disabled).toBe(true);

        el._setDatePart('year', '2024');
        await tick(el);
        expect(selects()[1].disabled).toBe(false);
        expect(selects()[2].disabled).toBe(true);

        el._setDatePart('month', '2');
        await tick(el);
        expect(selects()[2].disabled).toBe(false);
        // 2024 is a leap year, so February has to offer the 29th.
        expect(selects()[2].querySelectorAll('option')).toHaveLength(30);
    });

    // The pane is as often amending a date as asking for one, so it has to show
    // what it already holds — otherwise three unmarked rows read as unanswered.
    describe('a date already recorded', () => {
        const pad = n => String(n).padStart(2, '0');
        const now = new Date();
        const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

        const openPane = async readDate => {
            stubFetch();
            const el = await mount({ shelf: SHELF.ALREADY_READ, readDate });
            qa(el, '.group.shelves .row')[2].click();
            await tick(el);
            return el;
        };
        const marked = el => paneRows(el)
            .filter(r => r.getAttribute('aria-current') === 'true')
            .map(r => r.querySelector('.label').textContent);

        test('today\'s date marks Today', async() => {
            expect(marked(await openPane(today))).toEqual(['Today']);
        });

        test('a bare current year marks that year', async() => {
            expect(marked(await openPane(String(now.getFullYear())))).toEqual([`In ${now.getFullYear()}`]);
        });

        test('anything else marks Other date and shows the date on the row', async() => {
            const el = await openPane('1998-03-14');
            expect(marked(el)).toEqual(['Other date']);
            expect(q(el, '.date-toggle .count').textContent).toBe('Mar 14, 1998');
        });

        test('no date marks nothing', async() => {
            expect(marked(await openPane(null))).toEqual([]);
        });

        // A date the shortcuts cannot express is invisible behind a collapsed
        // row, so the pane opens on it.
        test('a date no shortcut can express opens the selects, seeded', async() => {
            const el = await openPane('1998-03-14');
            expect(el._pickingDate).toBe(true);
            expect(qa(el, '.select').map(s => s.value)).toEqual(['1998', '3', '14']);
        });

        test('a partial date seeds only the parts it knows', async() => {
            const el = await openPane('1998-03');
            expect(qa(el, '.select').map(s => s.value)).toEqual(['1998', '3', '']);
        });

        test('a date a shortcut covers leaves them closed', async() => {
            expect((await openPane(today))._pickingDate).toBe(false);
            expect((await openPane(String(now.getFullYear())))._pickingDate).toBe(false);
        });

        // Lit commits a select's own bindings before its children, so seeding
        // through the select's .value silently dropped; the selection rides on
        // each option instead. Clearing has to survive the same round trip.
        test('clearing the year blanks the selects it gated', async() => {
            const el = await openPane('1998-03-14');
            el._setDatePart('year', '');
            await tick(el);
            expect(qa(el, '.select').map(s => s.value)).toEqual(['', '', '']);
        });
    });

    test('other date is a disclosure, so pressing it again closes the selects', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);

        const toggle = () => checkInPane(el).querySelector('.date-toggle');
        // A down chevron, not a right one: nothing is being navigated to.
        expect(toggle().querySelector('.trail').getAttribute('name')).toBe('chevron-down');
        expect(toggle().getAttribute('aria-expanded')).toBe('false');

        toggle().click();
        await tick(el);
        expect(toggle().getAttribute('aria-expanded')).toBe('true');

        toggle().click();
        await tick(el);
        expect(toggle().getAttribute('aria-expanded')).toBe('false');
        expect(checkInPane(el).querySelectorAll('.select')).toHaveLength(0);
        // Closing the fields stays on the pane rather than backing out of it.
        expect(el._pane).toBe('checkIn');
    });

    test('Today still answers while the selects are open', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        otherDateRow(el).click();
        await tick(el);
        paneRows(el)[0].click();
        await tick(el);
        expect(JSON.parse(checkInWrites()[0].init.body).day).toBe(new Date().getDate());
    });

    test('clearing the year clears what it gated', async() => {
        stubFetch();
        const el = await mount();
        el._setDatePart('year', '2024');
        el._setDatePart('month', '6');
        el._setDatePart('day', '15');
        el._setDatePart('year', '');
        expect(el._date).toEqual({ year: '', month: '', day: '' });
    });

    test('a partial date saves as a partial date', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        otherDateRow(el).click();
        await tick(el);
        el._setDatePart('year', '2024');
        el._setDatePart('month', '6');
        await tick(el);
        checkInPane(el).querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
        await tick(el);
        const body = JSON.parse(checkInWrites()[0].init.body);
        expect([body.year, body.month, body.day]).toEqual([2024, 6, null]);
    });

    // Every other row on the pane replaces one date with another, so deleting
    // the event is the only way back to an unanswered question.
    describe('removing the date', () => {
        const openPane = async(props = {}) => {
            const el = await mount({ shelf: SHELF.ALREADY_READ, ...props });
            qa(el, '.group.shelves .row')[2].click();
            await tick(el);
            return el;
        };

        test('is offered only once a date is recorded', async() => {
            stubFetch();
            expect(clearDateLink(await openPane())).toBeNull();
            expect(clearDateLink(await openPane({ readDate: '2025', eventId: 12 }))).not.toBeNull();
        });

        test('deletes the event and unanswers the pane', async() => {
            stubFetch();
            const el = await openPane({ readDate: '2025', eventId: 12 });
            const events = [];
            el.addEventListener('ol-book-check-in', e => events.push(e.detail));
            clearDateLink(el).click();
            await tick(el);

            expect(calls.filter(c => c.url === '/check-ins/12' && c.init.method === 'DELETE')).toHaveLength(1);
            expect(el.readDate).toBeNull();
            expect(el.eventId).toBeNull();
            expect(events).toEqual([{ key: '/works/OL1W', date: null, eventId: null }]);
            // The book stays on the shelf; only the date went.
            expect(el.shelf).toBe(SHELF.ALREADY_READ);
            expect(el._pane).toBe('main');
        });

        test('a failed removal keeps the date', async() => {
            stubFetch({ failWith: 500 });
            const el = await openPane({ readDate: '2025', eventId: 12 });
            clearDateLink(el).click();
            await tick(el);
            expect(el.readDate).toBe('2025');
            expect(el.eventId).toBe(12);
        });
    });

    test('removing the book from its shelf drops the date the server deleted with it', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.ALREADY_READ, readDate: '2025', eventId: 12 });
        // The Remove-from-shelf link: for Already Read, clicking the shelf row
        // amends the date instead.
        q(el, '.clear-shelf').click();
        await tick(el);
        expect(el.shelf).toBeNull();
        expect(el.readDate).toBeNull();
        expect(el.eventId).toBeNull();
        // So the next check-in adds an event instead of amending event 12.
        el.shelf = SHELF.ALREADY_READ;
        await tick(el);
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        yearRows(el)[0].click();
        await tick(el);
        expect(JSON.parse(checkInWrites()[0].init.body).event_id).toBeNull();
    });

    test('a failed removal puts the date back', async() => {
        stubFetch({ failWith: 500 });
        const el = await mount({ shelf: SHELF.ALREADY_READ, readDate: '2025', eventId: 12 });
        q(el, '.clear-shelf').click();
        await tick(el);
        expect(el.shelf).toBe(SHELF.ALREADY_READ);
        expect(el.readDate).toBe('2025');
        expect(el.eventId).toBe(12);
    });

    test('a removal made outside the popover drops it too', async() => {
        stubFetch();
        const el = await mount({ shelf: SHELF.ALREADY_READ, readDate: '2025', eventId: 12 });
        // What the split button's main click does, applied by the surface.
        el.shelf = null;
        await tick(el);
        expect(el.readDate).toBeNull();
        expect(el.eventId).toBeNull();
    });

    test('Escape from the pane goes back rather than closing', async() => {
        stubFetch();
        const el = await mount();
        qa(el, '.group.shelves .row')[2].click();
        await tick(el);
        const event = new CustomEvent('ol-popover-close', { detail: { reason: 'escape' }, cancelable: true });
        q(el, 'ol-popover').dispatchEvent(event);
        await tick(el);
        expect(event.defaultPrevented).toBe(true);
        expect(el._pane).toBe('main');
    });
});
