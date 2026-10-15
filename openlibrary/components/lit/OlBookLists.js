import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import './OlIcon.js';
import './OLButton.js';
import { getLists, subscribeToLists, loadLists, removeListSeeds } from './utils/lists-store.js';
import { redirectToLogin } from './utils/books-api.js';
import { showToast } from './OlToastRegion.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { translate } from './utils/labels.js';

export const DEFAULT_LABELS = {
    onYourLists: 'On your lists',
    removeFromList: 'Remove from %(name)s',
    removedFromList: 'Removed from %(name)s',
    errorGeneric: 'Something went wrong. Please try again.'
};

/**
 * The reader's lists that hold this book, under the shelf button on a book or
 * author page.
 *
 * Rendered from the shared lists store, the same module instance the shelf
 * button's popover writes to, so a list added or removed there shows here at
 * once. Every list in the store is the reader's own, so rows carry no byline.
 *
 * A list counts if it holds one of the page's own keys: the work, or the
 * edition on screen. Other editions of the book are left to the popover, which
 * fetches them on open. Remove takes every one of those keys out of the list,
 * so a row always stands for the book, not a form of it.
 *
 * @element ol-book-lists
 *
 * @prop {Array<String>} seedKeys - The book's keys a list may hold: work and
 *     edition, or an author's key. Attribute: `seed-keys` (JSON).
 * @prop {Object} labels - Translated overrides for DEFAULT_LABELS (JSON).
 *
 * @fires ol-list-change - After the book is taken out of a list here.
 *     detail: { key, name, seedKeys, member: false }
 *
 * @example
 * <ol-book-lists seed-keys='["/works/OL1W", "/books/OL1M"]'></ol-book-lists>
 */
export class OlBookLists extends LitElement {
    static properties = {
        seedKeys: { type: Array, attribute: 'seed-keys' },
        labels: { type: Object },
        _lists: { state: true },
        _announcement: { state: true }
    };

    static styles = css`
        :host {
            display: block;
        }

        /* The gap under the shelf button is padding on the list, not a margin
           on the host, so an empty strip takes no space. */
        ul {
            margin: 0;
            padding: var(--spacing-sm) 0 0;
            list-style: none;
        }

        li {
            display: flex;
            align-items: center;
            gap: var(--spacing-2xs);
            min-height: var(--control-height-small);
            padding-block: var(--spacing-3xs);
            padding-inline-start: var(--spacing-2xs);
        }

        .icon {
            flex: none;
            color: var(--color-icon-muted);
        }

        /* One line: a long name ends in an ellipsis, and its title shows it whole. */
        a {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            color: var(--color-text);
            font-size: var(--font-size-body-small);
            text-decoration: none;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        a:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: var(--spacing-3xs);
        }

        .remove {
            flex: none;
        }

        .visually-hidden {
            position: absolute;
            width: 1px;
            height: 1px;
            overflow: hidden;
            clip-path: inset(50%);
            white-space: nowrap;
        }

        /* With a mouse the remove button sits over the row's end, hidden, and
           the name only gives up that width while the row is hovered or holds
           focus. It stays in the tab order, so Shift+Tab still reaches it. On
           touch there is no hover to wait for, so it keeps its place in flow. */
        @media (hover: hover) and (pointer: fine) {
            a:hover {
                text-decoration: underline;
            }

            li {
                position: relative;
            }

            .remove {
                position: absolute;
                inset-inline-end: 0;
                opacity: 0;
            }

            li:hover,
            li:focus-within {
                padding-inline-end: calc(var(--control-height-small) + var(--spacing-2xs));
            }

            li:hover .remove,
            li:focus-within .remove {
                opacity: 1;
            }
        }
    `;

    constructor() {
        super();
        this.seedKeys = [];
        this.labels = {};
        this._lists = getLists();
        this._announcement = '';
        this._order = [];
        this._removing = new Set();
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = subscribeToLists(() => this._setLists(getLists()));
        // A failed load leaves the strip empty; the popover reports failures.
        loadLists().then(
            lists => this._setLists(lists),
            () => {}
        );
    }

    /**
     * The store moves a changed list to the front; the strip keeps rows where
     * they are, so the row under the pointer stays the one it was. Lists new
     * to the strip go on top, where the store puts them.
     */
    _setLists(lists) {
        const keys = Object.keys(lists || {});
        const seen = new Set(this._order);
        this._order = [...keys.filter(key => !seen.has(key)), ...this._order.filter(key => key in (lists || {}))];
        this._lists = lists;
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    /** One row per list, with the page's keys that list holds. */
    get _rows() {
        if (!this._lists) return [];
        const seeds = new Set(this.seedKeys);
        return this._order
            .map(key => [key, this._lists[key]])
            .map(([key, list]) => ({ key, name: list.listName, seeds: list.members.filter(m => seeds.has(m)) }))
            .filter(row => row.seeds.length);
    }

    async _remove(row, index) {
        if (this._removing.has(row.key)) return;
        this._removing.add(row.key);
        try {
            await removeListSeeds(row.key, row.seeds);
        } catch (error) {
            if (error?.status === 401) return redirectToLogin();
            showToast(this.t('errorGeneric'), { type: 'error' });
            return;
        } finally {
            this._removing.delete(row.key);
        }
        this.dispatchEvent(
            new CustomEvent('ol-list-change', {
                bubbles: true,
                composed: true,
                detail: { key: row.key, name: row.name, seedKeys: row.seeds, member: false }
            })
        );
        trackEvent('Lists', 'RemoveSeed');
        // No toast: the row going says it happened. Screen readers hear it
        // from the live region instead.
        this._announcement = this.t('removedFromList', { name: row.name });
        // Keep keyboard focus in the strip, on the row that took its place.
        await this.updateComplete;
        const buttons = this.renderRoot.querySelectorAll('.remove');
        buttons[Math.min(index, buttons.length - 1)]?.focus();
    }

    render() {
        const rows = this._rows;
        // The live region stays rendered with no rows, so removing the last one is still announced.
        return html`
            ${
                rows.length
                    ? html`<ul aria-label=${this.t('onYourLists')}>
                          ${repeat(
                              rows,
                              row => row.key,
                              (row, index) =>
                                  html`<li data-key=${row.key}>
                                      <ol-icon class="icon" name="list" size="sm"></ol-icon>
                                      <a href=${row.key} title=${row.name}>${row.name}</a>
                                      <ol-button
                                          class="remove"
                                          shape="icon"
                                          variant="ghost"
                                          size="small"
                                          title=${this.t('removeFromList', { name: row.name })}
                                          aria-label=${this.t('removeFromList', { name: row.name })}
                                          @click=${() => this._remove(row, index)}
                                          ><ol-icon name="x" size="sm"></ol-icon
                                      ></ol-button>
                                  </li>`
                          )}
                      </ul>`
                    : nothing
            }
            <div class="visually-hidden" role="status">${this._announcement}</div>
        `;
    }
}

customElements.define('ol-book-lists', OlBookLists);
