/**
 * The "lists this book is on" strip under the shelf button on a book page.
 * Fed from the lists partial and kept current by the popover's events;
 * removal from the strip itself still goes through ShowcaseItem.
 *
 * @module lists/active-showcase
 */
import { getListPartials } from './ListService';
import { ShowcaseItem, createActiveShowcaseItem } from './ShowcaseItem';
import myBooksStore from '../my-books/store';
import { removeChildren } from '../utils';

/** The list's first member stands in for its cover, as the legacy strip did. */
function coverFor(list) {
    const first = list.members[0];
    if (!first) return undefined;
    return `https://covers.openlibrary.org/b/olid/${first.slice(first.indexOf('OL'))}-S.jpg`;
}

/**
 * @param {HTMLElement} container The `.already-lists` element, carrying the
 *     book's seed keys (work and edition) in `data-seed-keys`.
 */
export async function initActiveListsShowcase(container) {
    const seedKeys = new Set(JSON.parse(container.dataset.seedKeys));
    const showcases = myBooksStore.getShowcases();

    const has = (listKey, seedKey) => showcases.some(item => item.isShowcaseForListAndSeed(listKey, seedKey));

    const add = (listKey, seedKey, listName, cover) => {
        if (has(listKey, seedKey)) return;
        const li = createActiveShowcaseItem(listKey, seedKey, listName, cover);
        container.appendChild(li);
        const item = new ShowcaseItem(li);
        item.initialize();
        showcases.push(item);
    };

    const remove = (listKey, seedKey) => {
        for (const item of showcases.filter(item => item.isShowcaseForListAndSeed(listKey, seedKey))) {
            item.removeSelf();
        }
    };

    document.addEventListener('ol-list-created', (e) => {
        const { key, name, seedKey } = e.detail;
        if (seedKeys.has(seedKey)) add(key, seedKey, name);
    });
    document.addEventListener('ol-list-change', (e) => {
        const { key, name, seedKey, member } = e.detail;
        if (!seedKeys.has(seedKey)) return;
        if (member) add(key, seedKey, name);
        else remove(key, seedKey);
    });

    const { listData } = await getListPartials().then(response => response.json());
    removeChildren(container);
    for (const [listKey, list] of Object.entries(listData)) {
        for (const seedKey of list.members) {
            if (seedKeys.has(seedKey)) add(listKey, seedKey, list.listName, coverFor(list));
        }
    }
}
