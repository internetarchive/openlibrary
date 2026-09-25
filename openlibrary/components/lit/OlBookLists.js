import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import './OlIcon.js';
import './OLButton.js';
import { getLists, subscribeToLists, loadLists, toggleListSeed } from './utils/lists-store.js';
import { redirectToLogin } from './utils/books-api.js';
import { showToast } from './OlToastRegion.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { translate } from './utils/labels.js';

export const DEFAULT_LABELS = {
    onYourLists: 'On your lists',
    removeFromList: 'Remove from %(name)s',
    removedFromList: 'Removed from %(name)s',
    errorGeneric: 'Something went wrong. Please try again.',
};

/**
 * The reader's lists that hold this book, under the shelf button on a book or
 * author page.
 *
 * Rendered from the shared lists store, the same module instance the shelf
 * button's popover writes to, so a list added or removed there shows here at
 * once. Every list in the store is the reader's own, so rows carry no byline.
 *
 * @element ol-book-lists
 *
 * @prop {Array<String>} seedKeys - The book's keys a list may hold: work and
 *     edition, or an author's key. Attribute: `seed-keys` (JSON).
 * @prop {Object} labels - Translated overrides for DEFAULT_LABELS (JSON).
 *
 * @fires ol-list-change - After the book is taken out of a list here.
 *     detail: { key, name, seedKey, member: false }
 *
 * @example
 * <ol-book-lists seed-keys='["/works/OL1W", "/books/OL1M"]'></ol-book-lists>
 */
export class OlBookLists extends LitElement {
    static properties = {
        seedKeys: { type: Array, attribute: 'seed-keys' },
        labels: { type: Object },
        _lists: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }

        /* The gap under the shelf button lives here, not on the host, so an
           empty strip takes no space. */
        ul {
            margin: var(--spacing-sm) 0 0;
            padding: 0;
            list-style: none;
        }

        li {
            display: flex;
            align-items: center;
            gap: var(--spacing-2xs);
            min-height: 28px;
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

        a:hover {
            text-decoration: underline;
        }

        a:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
            border-radius: var(--border-radius-sm);
        }

        .remove {
            flex: none;
            color: var(--color-icon-muted);
        }

        /* With a mouse the remove button sits over the row's end, hidden, and
           the name only gives up that width while the row is hovered or holds
           focus. It stays in the tab order, so Shift+Tab still reaches it. On
           touch there is no hover to wait for, so it keeps its place in flow. */
        @media (hover: hover) and (pointer: fine) {
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
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = subscribeToLists(() => { this._lists = getLists(); });
        // A failed load leaves the strip empty; the popover reports failures.
        loadLists().then(lists => { this._lists = lists; }, () => {});
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    /** One row per list, with every one of this book's keys that list holds. */
    get _rows() {
        if (!this._lists) return [];
        const seeds = new Set(this.seedKeys);
        return Object.entries(this._lists)
            .map(([key, list]) => ({ key, name: list.listName, seeds: list.members.filter(m => seeds.has(m)) }))
            .filter(row => row.seeds.length);
    }

    async _remove(row, index) {
        try {
            for (const seedKey of row.seeds) {
                await toggleListSeed(row.key, seedKey, false);
                this.dispatchEvent(new CustomEvent('ol-list-change', {
                    bubbles: true,
                    composed: true,
                    detail: { key: row.key, name: row.name, seedKey, member: false },
                }));
            }
        } catch (error) {
            if (error?.status === 401) return redirectToLogin();
            showToast(this.t('errorGeneric'), { type: 'error' });
            return;
        }
        trackEvent('Lists', 'RemoveSeed');
        showToast(this.t('removedFromList', { name: row.name }), { type: 'success' });
        // Keep keyboard focus in the strip: the row it was on is gone.
        await this.updateComplete;
        const buttons = this.renderRoot.querySelectorAll('.remove');
        buttons[Math.min(index, buttons.length - 1)]?.focus();
    }

    render() {
        const rows = this._rows;
        if (!rows.length) return nothing;
        return html`
            <ul aria-label=${this.t('onYourLists')}>${repeat(rows, row => row.key, (row, index) => html`<li>
                        <ol-icon class="icon" name="list" size="sm"></ol-icon>
                        <a href=${row.key} title=${row.name}>${row.name}</a>
                        <ol-button
                            class="remove"
                            shape="icon"
                            variant="ghost"
                            size="small"
                            aria-label=${this.t('removeFromList', { name: row.name })}
                            @click=${() => this._remove(row, index)}
                        ><ol-icon name="x" size="sm"></ol-icon></ol-button>
                    </li>`)}</ul>
        `;
    }
}

customElements.define('ol-book-lists', OlBookLists);
