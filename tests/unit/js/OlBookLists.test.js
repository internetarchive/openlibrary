/**
 * Unit tests for <ol-book-lists>: it renders the reader's lists that hold the
 * book from the shared lists store and follows every change made through it.
 * Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlBookLists.js';
import { createUserList, resetListsStore, toggleListSeed } from '../../../openlibrary/components/lit/utils/lists-store.js';

const WORK = '/works/OL1W';
const EDITION = '/books/OL1M';
const OTHER = '/books/OL2M';
const LIST = '/people/openlibrary/lists/OL1L';

function jsonResponse(body) {
    return { ok: true, status: 200, json: async () => body };
}

function stubFetch(listData) {
    global.fetch = vi.fn(async url => {
        if (String(url).includes('MyBooksDropperLists')) return jsonResponse({ listData });
        return jsonResponse({ key: '/people/openlibrary/lists/OL9L' });
    });
}

async function mount(listData, seedKeys = [WORK, EDITION]) {
    stubFetch(listData);
    const el = document.createElement('ol-book-lists');
    el.seedKeys = seedKeys;
    document.body.appendChild(el);
    await vi.waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await new Promise(resolve => setTimeout(resolve));
    await el.updateComplete;
    return el;
}

const names = el => [...el.shadowRoot.querySelectorAll('li a')].map(a => a.textContent);
const notes = el => [...el.shadowRoot.querySelectorAll('li')].map(li => li.querySelector('.note')?.textContent ?? null);
const removeLabel = el => el.shadowRoot.querySelector('.remove').getAttribute('aria-label');
const status = el => el.shadowRoot.querySelector('[role="status"]').textContent;
const removed = () => global.fetch.mock.calls.filter(([url]) => String(url).endsWith('/seeds.json')).map(([, init]) => JSON.parse(init.body).remove[0].key);

describe('ol-book-lists', () => {
    beforeEach(() => {
        resetListsStore();
        document.body.innerHTML = '';
    });

    test('renders one row per list holding the book, with one request', async () => {
        const el = await mount({
            [LIST]: { listName: 'Mine', members: [WORK, EDITION] },
            '/people/openlibrary/lists/OL2L': { listName: 'Other', members: ['/works/OL3W'] }
        });
        expect(names(el)).toEqual(['Mine']);
        expect(el.shadowRoot.querySelector('li a').getAttribute('href')).toBe(LIST);
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    test('renders nothing when no list holds the book', async () => {
        const el = await mount({});
        expect(el.shadowRoot.querySelector('ul')).toBeNull();
    });

    test('follows the store: a created list appears, an untick removes', async () => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [WORK] } });

        await createUserList('/people/openlibrary', 'New', EDITION);
        await el.updateComplete;
        expect(names(el)).toEqual(['New', 'Mine']);

        await toggleListSeed(LIST, WORK, false);
        await el.updateComplete;
        expect(names(el)).toEqual(['New']);
    });

    test('ignores a list holding only another edition, without asking for editions', async () => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [OTHER] } });
        expect(names(el)).toEqual([]);
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    test('on an edition page, a list holding the work too keeps the work', async () => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [WORK, EDITION] } });
        expect(notes(el)).toEqual(['Any edition']);
        expect(removeLabel(el)).toBe('Remove this edition from Mine');

        el.shadowRoot.querySelector('.remove').click();
        await vi.waitFor(() => expect(status(el)).toBe('Removed this edition from Mine. The book is still on it.'));
        expect(removed()).toEqual([EDITION]);
        expect(names(el)).toEqual(['Mine']);
        expect(notes(el)).toEqual(['Any edition']);
        expect(removeLabel(el)).toBe('Remove from Mine');
        expect(el.shadowRoot.activeElement).toBe(el.shadowRoot.querySelector('.remove'));
    });

    test('removing the only key takes the row out', async () => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [EDITION, OTHER] } });
        expect(notes(el)).toEqual([null]);
        expect(removeLabel(el)).toBe('Remove from Mine');

        el.shadowRoot.querySelector('.remove').click();
        await vi.waitFor(() => expect(names(el)).toEqual([]));
        expect(removed()).toEqual([EDITION]);
        expect(status(el)).toBe('Removed from Mine');
    });

    test('a row keeps its place after a partial remove', async () => {
        const el = await mount({
            '/people/openlibrary/lists/OL2L': { listName: 'First', members: [EDITION] },
            [LIST]: { listName: 'Second', members: [WORK, EDITION] }
        });
        el.shadowRoot.querySelectorAll('.remove')[1].click();
        await vi.waitFor(() => expect(status(el)).toContain('Second'));
        expect(names(el)).toEqual(['First', 'Second']);
    });
});
