import { initListShowcase } from '../../../openlibrary/plugins/openlibrary/js/lists/list-showcase.js';
import { getShowcases } from '../../../openlibrary/plugins/openlibrary/js/lists/ShowcaseItem.js';
import { createUserList, resetListsStore, toggleListSeed } from '../../../openlibrary/components/lit/utils/lists-store.js';
import { showcaseI18nInput } from './sample-html/lists-test-data';

const WORK = '/works/OL1W';
const EDITION = '/books/OL1M';
const LIST = '/people/openlibrary/lists/OL1L';

function jsonResponse(body) {
    return { ok: true, status: 200, json: async() => body };
}

function setup(listData) {
    document.body.innerHTML = `${showcaseI18nInput}
        <ul class="already-lists" data-seed-keys='${JSON.stringify([WORK, EDITION])}'>
            <div class="list-overview-loading-indicator">Loading</div>
        </ul>`;
    global.fetch = vi.fn(async(url) => {
        if (String(url).includes('MyBooksDropperLists')) return jsonResponse({ listData });
        return jsonResponse({ key: '/people/openlibrary/lists/OL9L' });
    });
    return document.querySelector('.already-lists');
}

const chips = (container) => [...container.querySelectorAll('.actionable-item')].map(li => li.querySelector('input[name=seed-key]').value);

describe('initListShowcase', () => {
    beforeEach(() => {
        resetListsStore();
        getShowcases().length = 0;
    });

    test('renders one chip per matching seed from the shared store, with one request', async() => {
        const container = setup({
            [LIST]: { listName: 'Mine', members: [WORK, '/works/OL2W'] },
            '/people/openlibrary/lists/OL2L': { listName: 'Other', members: ['/works/OL3W'] },
        });
        await initListShowcase(container);
        expect(chips(container)).toEqual([WORK]);
        expect(container.querySelector('.list-overview-loading-indicator')).toBeNull();
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    test('follows the store: a created list appears, an untick removes', async() => {
        const container = setup({ [LIST]: { listName: 'Mine', members: [WORK] } });
        await initListShowcase(container);

        await createUserList('/people/openlibrary', 'New', EDITION);
        expect(chips(container)).toEqual([WORK, EDITION]);

        await toggleListSeed(LIST, WORK, false);
        expect(chips(container)).toEqual([EDITION]);
    });

    test('a failed load keeps the loading indicator', async() => {
        const container = setup({});
        global.fetch = vi.fn(async() => { throw new Error('offline'); });
        await initListShowcase(container);
        expect(container.querySelector('.list-overview-loading-indicator')).not.toBeNull();
    });
});
