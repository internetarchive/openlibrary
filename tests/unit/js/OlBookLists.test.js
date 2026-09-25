/**
 * Unit tests for <ol-book-lists>: it renders the reader's lists that hold the
 * book from the shared lists store and follows every change made through it.
 * Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlBookLists.js';
import { createUserList, resetListsStore, toggleListSeed } from '../../../openlibrary/components/lit/utils/lists-store.js';
import { resetWorkEditionsCache } from '../../../openlibrary/components/lit/utils/book-editions.js';

const WORK = '/works/OL1W';
const EDITION = '/books/OL1M';
const OTHER = '/books/OL2M';
const THIRD = '/books/OL3M';
const LIST = '/people/openlibrary/lists/OL1L';

function jsonResponse(body) {
    return { ok: true, status: 200, json: async() => body };
}

function stubFetch(listData) {
    global.fetch = vi.fn(async(url) => {
        if (String(url).includes('MyBooksDropperLists')) return jsonResponse({ listData });
        if (String(url).includes('WorkEditions')) return jsonResponse({ editions: ['OL1M', 'OL2M', 'OL3M'] });
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
const editionFetches = () => global.fetch.mock.calls.filter(([url]) => String(url).includes('WorkEditions')).length;
const removed = () => global.fetch.mock.calls
    .filter(([url]) => String(url).endsWith('/seeds.json'))
    .map(([, init]) => JSON.parse(init.body).remove[0].key);

describe('ol-book-lists', () => {
    beforeEach(() => {
        resetListsStore();
        resetWorkEditionsCache();
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

    test('asks for editions only when a list holds one this page does not know', async() => {
        await mount({ [LIST]: { listName: 'Mine', members: [WORK, EDITION, '/works/OL9W'] } });
        expect(editionFetches()).toBe(0);
    });

    test('shows a list holding another edition, noted, and remove takes that edition out', async() => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [OTHER] } });
        expect(names(el)).toEqual(['Mine']);
        expect(notes(el)).toEqual(['1 other edition']);
        expect(editionFetches()).toBe(1);
        expect(removeLabel(el)).toBe('Remove 1 other edition from Mine');

        el.shadowRoot.querySelector('.remove').click();
        await vi.waitFor(() => expect(names(el)).toEqual([]));
        expect(removed()).toEqual([OTHER]);
        expect(status(el)).toBe('Removed from Mine');
    });

    test('on an edition page, a list holding more loses only this edition', async() => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [EDITION, OTHER] } });
        expect(removeLabel(el)).toBe('Remove this edition from Mine');

        el.shadowRoot.querySelector('.remove').click();
        await vi.waitFor(() => expect(status(el)).toBe('Removed this edition from Mine. The book is still on it.'));
        expect(removed()).toEqual([EDITION]);
        expect(names(el)).toEqual(['Mine']);
        expect(notes(el)).toEqual(['1 other edition']);
        expect(removeLabel(el)).toBe('Remove 1 other edition from Mine');
        expect(el.shadowRoot.activeElement).toBe(el.shadowRoot.querySelector('.remove'));
    });

    test('a row keeps its place after a partial remove', async() => {
        const el = await mount({
            '/people/openlibrary/lists/OL2L': { listName: 'First', members: [EDITION] },
            [LIST]: { listName: 'Second', members: [EDITION, OTHER] },
        });
        el.shadowRoot.querySelectorAll('.remove')[1].click();
        await vi.waitFor(() => expect(status(el)).toContain('Second'));
        expect(names(el)).toEqual(['First', 'Second']);
    });

    test('a list holding only this edition and the bare work keeps the work', async() => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [WORK, EDITION] } });
        expect(notes(el)).toEqual(['Any edition']);
        el.shadowRoot.querySelector('.remove').click();
        await vi.waitFor(() => expect(removed()).toEqual([EDITION]));
        await el.updateComplete;
        expect(names(el)).toEqual(['Mine']);
        expect(removeLabel(el)).toBe('Remove from Mine');
    });

    test('on a work page, remove takes every form of the book and says how many', async() => {
        const el = await mount({ [LIST]: { listName: 'Mine', members: [WORK, EDITION, THIRD] } }, [WORK]);
        expect(notes(el)).toEqual(['2 other editions']);
        expect(removeLabel(el)).toBe('Remove the work and 2 editions from Mine');

        el.shadowRoot.querySelector('.remove').click();
        await vi.waitFor(() => expect(names(el)).toEqual([]));
        expect(removed()).toEqual([WORK, EDITION, THIRD]);
    });
});
