/**
 * The "lists this book is on" strip under the shelf button on a book or
 * author page. Fed from the lists partial and kept current by the popover's
 * events; removal from the strip itself still goes through ShowcaseItem.
 *
 * @module lists/active-showcase
 */
import { getListPartials } from './ListService';
import { ShowcaseItem, createActiveShowcaseItem, getShowcases } from './ShowcaseItem';
import { removeChildren } from '../utils';

/** The list's first member stands in for its cover, as the legacy strip did. */
function coverFor(list) {
    const first = list.members[0];
    if (!first) return undefined;
    return `https://covers.openlibrary.org/b/olid/${first.slice(first.indexOf('OL'))}-S.jpg`;
}

/**
 * @param {HTMLElement} container The `.already-lists` element, carrying the
 *     seed keys (work and edition, or author) in `data-seed-keys`.
 */
export async function initActiveListsShowcase(container) {
    const seedKeys = new Set(JSON.parse(container.dataset.seedKeys));

    const has = (listKey, seedKey) => getShowcases().some(item => item.isShowcaseForListAndSeed(listKey, seedKey));

    const add = (listKey, seedKey, listName, cover) => {
        if (has(listKey, seedKey)) return;
        const li = createActiveShowcaseItem(listKey, seedKey, listName, cover);
        container.appendChild(li);
        new ShowcaseItem(li).initialize();
    };

    const remove = (listKey, seedKey) => {
        for (const item of getShowcases().filter(item => item.isShowcaseForListAndSeed(listKey, seedKey))) {
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
