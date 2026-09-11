/**
 * @module lists/ShowcaseItem.js
 */
import { removeItem } from './ListService';

/** Every ShowcaseItem on the page, so a removal can take its twins with it. */
const showcases = [];

/** @returns {ShowcaseItem[]} */
export function getShowcases() {
    return showcases;
}

/**
 * Represents an actionable list showcase item.
 *
 * A list showcase displays a collection of lists that
 * contain the same seed object.  An actionable showcase item
 * includes an affordance that removes the seed from a specific
 * list.
 *
 * The active showcase is the strip of lists under a book's or
 * author's shelf button (`.already-lists`), kept current by
 * lists/active-showcase.js as the popover adds and removes.
 * @class
 */
export class ShowcaseItem {
    /**
     * Creates a new `ShowcaseItem` obect.
     *
     * Sets references needed for this ShowcaseItem's functionality.
     *
     * @param {HTMLElement} showcaseElem
     */
    constructor(showcaseElem) {
        /**
         * Reference to the root element of this component.
         * @member {HTMLElement}
         */
        this.showcaseElem = showcaseElem;

        /**
         * `true` if this object represents the active lists showcase.
         * @member {boolean}
         */
        this.isActiveShowcase = showcaseElem.parentElement.classList.contains('already-lists');

        /**
         * Reference to the affordance which removes an item from this list.
         * @member {HTMLElement}
         */
        this.removeFromListAffordance = showcaseElem.querySelector('.remove-from-list');

        /**
         * Unique identifier for the showcased list.
         * @member {string}
         */
        this.listKey = this.removeFromListAffordance.dataset.listKey;

        /**
         * Unique identifier for the showcased list member.
         * @member {string}
         */
        this.seedKey = showcaseElem.querySelector('input[name=seed-key]').value;

        /**
         * The list item's type.
         * @member {'subject'|'edition'|'work'|'author'}
         */
        this.type = showcaseElem.querySelector('input[name=seed-type]').value;

        /**
         * `true` if this list item is a subject.
         * @member {boolean}
         */
        this.isSubject = this.type === 'subject';

        /**
         * `true` if this list item is a work
         * @member {boolean}
         */
        this.isWork = !this.isSubject && this.seedKey.slice(-1) === 'W';

        /**
         * `POST` request-ready representation of the list's seed key.
         * @member {string|object}
         */
        this.seed;
        if (this.isSubject) {
            this.seed = this.seedKey;
        } else {
            this.seed = { key: this.seedKey };
        }
    }

    /**
     * Attaches click listeners to the showcase item's "Remove from list"
     * affordance, and registers the item with the page.
     */
    initialize() {
        showcases.push(this);
        this.removeFromListAffordance.addEventListener('click', (event) => {
            event.preventDefault();
            this.removeShowcaseItem();
        });
    }

    /**
     * Sends request to remove an item from a list, then updates the view.
     *
     * Removes any affiliated showcase items from the DOM.
     */
    async removeShowcaseItem() {
        await removeItem(this.listKey, this.seed)
            .then(response => response.json())
            .then(() => {
                this.removeSelf();
                // Remove other showcase items that are associated with the list and seed key:
                for (const showcase of [...showcases]) {
                    if (showcase.isShowcaseForListAndSeed(this.listKey, this.seedKey)) {
                        showcase.removeSelf();
                    }
                }
            });
    }

    /**
     * Removes associated showcase item from the DOM, and itself from the
     * page's showcases.
     */
    removeSelf() {
        const thisIndex = showcases.indexOf(this);
        if (thisIndex >= 0) {
            this.showcaseElem.remove();
            showcases.splice(thisIndex, 1);
        }
    }

    /**
     * Determines if this showcase item is linked to the given keys.
     *
     * @param {string} listKey
     * @param {string} seedKey
     * @return {boolean} `true` if the given keys match this item's keys
     */
    isShowcaseForListAndSeed(listKey, seedKey) {
        return (this.listKey === listKey) && (this.seedKey === seedKey);
    }
}

/**
 * References localized strings needed for new
 * showcase items.
 * @type {Record<string, string>}
 */
let i18nStrings;

const DEFAULT_COVER_URL = '/static/images/icons/avatar_book-sm.png';

/**
 * Returns the inferred type of the given seed key.
 *
 * @param {string} seed
 * @returns {string} Type of the given seed key.
 */
function getSeedType(seed) {
    // XXX : validate input?
    if (seed[0] !== '/') {
        return 'subject';
    }
    if (seed.endsWith('M')) {
        return 'edition';
    }
    if (seed.endsWith('W')) {
        return 'work';
    }
    if (seed.endsWith('A')) {
        return 'author';
    }
}

/**
 * Creates and returns a new active list showcase item element.
 *
 * Populates `i18nStrings` when this function is first called.
 *
 * @param {string} listKey
 * @param {string} seedKey
 * @param {string} listTitle
 * @param {string} [coverUrl]
 * @returns {HTMLLIElement}
 */
export function createActiveShowcaseItem(listKey, seedKey, listTitle, coverUrl = DEFAULT_COVER_URL) {
    if (!i18nStrings) {
        const i18nInput = document.querySelector('input[name=list-i18n-strings]');
        i18nStrings = JSON.parse(i18nInput.value);
    }

    const splitKey = listKey.split('/');
    const userKey = `/${splitKey[1]}/${splitKey[2]}`;
    const seedType = getSeedType(seedKey);

    const itemMarkUp = `<span class="image">
                <a href="${listKey}"><img src="${coverUrl}" alt="${i18nStrings['cover_of']}${listTitle}" title="${i18nStrings['cover_of']}${listTitle}"/></a>
            </span>
            <span class="data">
                <span class="label">
                    <a href="${listKey}" data-list-title="${listTitle}" title="${i18nStrings['see_this_list']}">${listTitle}</a>
                    <input type="hidden" name="seed-title" value="${listTitle}"/>
                    <input type="hidden" name="seed-key" value="${seedKey}"/>
                    <input type="hidden" name="seed-type" value="${seedType}"/>
                    <a href="${listKey}" class="remove-from-list red smaller arial plain" data-list-key="${listKey}" title="${i18nStrings['remove_from_list']}">[X]</a>
                </span>
                <span class="owner">${i18nStrings['from']} <a href="${userKey}">${i18nStrings['you']}</a></span>
            </span>`;

    const li = document.createElement('li');
    li.classList.add('actionable-item');
    li.dataset.listKey = listKey;
    li.innerHTML = itemMarkUp;

    return li;
}
