/**
 * Unit tests for <ol-book-lists>: it renders the reader's lists that hold the
 * book from the shared lists store and follows every change made through it.
 * Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlBookLists.js';
import { createUserList, resetListsStore, toggleListSeed } from '../../../openlibrary/components/lit/utils/lists-store.js';

const WORK = '/works/OL1W';
const EDITION = '/books/OL1M';
const LIST = '/people/openlibrary/lists/OL1L';

function jsonResponse(body) {
    return { ok: true, status: 200, json: async() => body };
}

function stubFetch(listData) {
    global.fetch = vi.fn(async(url) => {
        if (String(url).includes('MyBooksDropperLists')) return jsonResponse({ listData });
        return jsonResponse({ key: '/people/openlibrary/lists/OL9L' });
    });
}

async function mount(listData) {
    stubFetch(listData);
    const el = document.createElement('ol-book-lists');
    el.seedKeys = [WORK, EDITION];
    document.body.appendChild(el);
    await vi.waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await new Promise(resolve => setTimeout(resolve));
    await el.updateComplete;
    return el;
}

const names = el => [...el.shadowRoot.querySelectorAll('li a')].map(a => a.textContent);

describe('ol-book-lists', () => {
    beforeEach(() => {
        resetListsStore();
        document.body.innerHTML = '';
    });

    test('renders one row per list holding the book, with one request', async() => {
        const el = await mount({
            [LIST]: { listName: 'Mine', members: [WORK, EDITION] },
            '/people/openlibrary/lists/OL2L': { listName: 'Other', members: ['/works/OL3W'] },
        });
        expect(names(el)).toEqual(['Mine']);
        expect(el.shadowRoot.querySelector('li a').getAttribute('href')).toBe(LIST);
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    test('renders nothing when no list holds the book', async() => {
        const el = await mount({});
        expect(el.shadowRoot.querySelector('ul')).toBeNull();
    });

    test('follows the store: a created list appears, an untick removes', async() => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [WORK] } });

        await createUserList('/people/openlibrary', 'New', EDITION);
        await el.updateComplete;
        expect(names(el)).toEqual(['New', 'Mine']);

        await toggleListSeed(LIST, WORK, false);
        await el.updateComplete;
        expect(names(el)).toEqual(['New']);
    });

    test('remove takes every key of the book out of the list', async() => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [WORK, EDITION] } });
        el.shadowRoot.querySelector('.remove').click();
        await vi.waitFor(() => expect(names(el)).toEqual([]));
        const bodies = global.fetch.mock.calls
            .filter(([url]) => String(url).endsWith('/seeds.json'))
            .map(([, init]) => JSON.parse(init.body));
        expect(bodies).toEqual([{ remove: [{ key: WORK }] }, { remove: [{ key: EDITION }] }]);
    });
});
