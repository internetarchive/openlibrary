/**
 * The "lists this book is on" strip under the shelf button on a book or
 * author page. Rendered from the page's shared lists store, so it costs no
 * request of its own and follows every change a popover makes; removal from
 * the strip itself still goes through ShowcaseItem.
 *
 * @module lists/list-showcase
 */
import { getLists, loadLists, subscribeToLists } from '../../../../components/lit/utils/lists-store.js';
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
export async function initListShowcase(container) {
    const seedKeys = new Set(JSON.parse(container.dataset.seedKeys));

    const mine = () => getShowcases().filter(item => container.contains(item.showcaseElem));

    const add = (listKey, seedKey, listName, cover) => {
        if (mine().some(item => item.isShowcaseForListAndSeed(listKey, seedKey))) return;
        const li = createActiveShowcaseItem(listKey, seedKey, listName, cover);
        container.appendChild(li);
        new ShowcaseItem(li).initialize();
    };

    // Reconcile the strip with the store: add what is missing, drop what is gone.
    const render = () => {
        const lists = getLists();
        if (!lists) return;
        const wanted = new Set();
        for (const [listKey, list] of Object.entries(lists)) {
            for (const seedKey of list.members) {
                if (!seedKeys.has(seedKey)) continue;
                wanted.add(`${listKey} ${seedKey}`);
                add(listKey, seedKey, list.listName, coverFor(list));
            }
        }
        for (const item of mine()) {
            if (!wanted.has(`${item.listKey} ${item.seedKey}`)) item.removeSelf();
        }
    };

    try {
        await loadLists();
    } catch {
        return; // the loading indicator stays; the popover reports the failure
    }
    removeChildren(container);
    render();
    subscribeToLists(render);
}
