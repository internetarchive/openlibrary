import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import './OlIcon.js';
import './OLButton.js';
import { getLists, subscribeToLists, loadLists, toggleListSeed } from './utils/lists-store.js';
import { loadWorkEditionKeys, otherForm } from './utils/book-editions.js';
import { redirectToLogin } from './utils/books-api.js';
import { showToast } from './OlToastRegion.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { translate } from './utils/labels.js';

export const DEFAULT_LABELS = {
    onYourLists: 'On your lists',
    otherEditions: { one: '%(count)s other edition', other: '%(count)s other editions' },
    anyEdition: 'Any edition',
    removeFromList: 'Remove from %(name)s',
    removeThisEdition: 'Remove this edition from %(name)s',
    removeEditions: { one: 'Remove %(count)s edition from %(name)s', other: 'Remove %(count)s editions from %(name)s' },
    removeOtherEditions: { one: 'Remove %(count)s other edition from %(name)s', other: 'Remove %(count)s other editions from %(name)s' },
    removeWorkAndEditions: { one: 'Remove the work and %(count)s edition from %(name)s', other: 'Remove the work and %(count)s editions from %(name)s' },
    removedFromList: 'Removed from %(name)s',
    removedThisEdition: 'Removed this edition from %(name)s. The book is still on it.',
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
 * A list counts if it holds the book in any form: this edition, another
 * edition, or the bare work. Rows note the other forms the way the popover
 * does. On an edition page, remove takes out this edition only when the list
 * holds more; otherwise it takes out every form the row stands for.
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
        _editionKeys: { state: true },
        _announcement: { state: true },
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
            padding-block: var(--spacing-3xs);
            padding-inline-start: var(--spacing-2xs);
        }

        .icon {
            flex: none;
            color: var(--color-icon-muted);
        }

        /* The name, and under it any note, share the row's free width. */
        .text {
            display: flex;
            flex: 1;
            flex-direction: column;
            min-width: 0;
        }

        /* One line: a long name ends in an ellipsis, and its title shows it whole. */
        a {
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

        /* A small line under the name, as in the popover, so the name keeps the width. */
        .note {
            overflow: hidden;
            line-height: 1.3;
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-small);
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .remove {
            flex: none;
            color: var(--color-icon-muted);
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
        // Null while another edition's membership is unknown; the strip waits
        // for it rather than adding a row after it first appears.
        this._editionKeys = [];
        this._announcement = '';
        this._order = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = subscribeToLists(() => this._setLists(getLists()));
        // A failed load leaves the strip empty; the popover reports failures.
        loadLists().then(lists => this._setLists(lists), () => {});
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
        this._loadEditionsIfNeeded();
    }

    get _workKey() {
        return this.seedKeys.find(key => key.startsWith('/works/'));
    }

    /** The edition this page is for; none on a work or author page. */
    get _editionKey() {
        return this.seedKeys.find(key => key.startsWith('/books/'));
    }

    /** The key this page records, as the shelf popover picks it. */
    get _pageKey() {
        return this._editionKey || this._workKey || this.seedKeys[0];
    }

    /**
     * Fetch the work's editions only when a list holds an edition this page
     * does not already know, so most readers pay nothing for it.
     */
    _loadEditionsIfNeeded() {
        if (this._editionsRequested || !this._lists || !this._workKey) return;
        const seeds = new Set(this.seedKeys);
        const unknown = Object.values(this._lists).some(list => list.members.some(key => key.startsWith('/books/') && !seeds.has(key)));
        if (!unknown) return;
        this._editionsRequested = true;
        this._editionKeys = null;
        loadWorkEditionKeys(this._workKey).then(keys => { this._editionKeys = keys; });
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
        if (!this._lists || !this._editionKeys) return [];
        const editionKeys = this._editionKeys;
        const seeds = new Set([...this.seedKeys, ...editionKeys]);
        const match = { seedKey: this._pageKey, workKey: this._workKey, editionKeys };
        return this._order
            .map(key => [key, this._lists[key]])
            .map(([key, list]) => ({
                key,
                name: list.listName,
                seeds: list.members.filter(m => seeds.has(m)),
                other: otherForm(list.members, match),
            }))
            .filter(row => row.seeds.length)
            .map(row => ({ ...row, ...this._removal(row) }));
    }

    /**
     * What remove takes out of a row, and the label that says so. On an
     * edition page a list holding this edition and more loses this edition
     * only; anything else loses every form of the book the row stands for.
     */
    _removal(row) {
        const pageKey = this._pageKey;
        const workKey = this._workKey;
        const vars = { name: row.name };
        if (this._editionKey && row.seeds.includes(pageKey) && row.seeds.length > 1) {
            return { targets: [pageKey], partial: true, label: this.t('removeThisEdition', vars) };
        }
        const targets = row.seeds;
        const count = targets.filter(key => key !== pageKey && key !== workKey).length;
        let label;
        if (!count) label = this.t('removeFromList', vars);
        else if (targets.includes(workKey)) label = this.t('removeWorkAndEditions', { ...vars, count });
        else label = this.t(this._editionKey ? 'removeOtherEditions' : 'removeEditions', { ...vars, count });
        return { targets, partial: false, label };
    }

    async _remove(row, index) {
        try {
            for (const seedKey of row.targets) {
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
        // No toast: the row going, or its note changing, says it happened.
        // Screen readers hear it from the live region instead.
        this._announcement = this.t(row.partial ? 'removedThisEdition' : 'removedFromList', { name: row.name });
        // Keep keyboard focus in the strip: on the row if it stayed, else the next one.
        await this.updateComplete;
        const same = this.renderRoot.querySelector(`li[data-key="${CSS.escape(row.key)}"] .remove`);
        const buttons = this.renderRoot.querySelectorAll('.remove');
        (same || buttons[Math.min(index, buttons.length - 1)])?.focus();
    }

    _renderNote(other) {
        if (!other) return nothing;
        const text = other.kind === 'edition' ? this.t('otherEditions', { count: other.count }) : this.t('anyEdition');
        return html`<span class="note">${text}</span>`;
    }

    render() {
        const rows = this._rows;
        // The live region stays rendered with no rows, so removing the last one is still announced.
        return html`
            ${rows.length ? html`<ul aria-label=${this.t('onYourLists')}>${repeat(rows, row => row.key, (row, index) => html`<li data-key=${row.key}>
                        <ol-icon class="icon" name="list" size="sm"></ol-icon>
                        <span class="text">
                            <a href=${row.key} title=${row.name}>${row.name}</a>
                            ${this._renderNote(row.other)}
                        </span>
                        <ol-button
                            class="remove"
                            shape="icon"
                            variant="ghost"
                            size="small"
                            title=${row.label}
                            aria-label=${row.label}
                            @click=${() => this._remove(row, index)}
                        ><ol-icon name="x" size="sm"></ol-icon></ol-button>
                    </li>`)}</ul>` : nothing}
            <div class="visually-hidden" role="status">${this._announcement}</div>
        `;
    }
}

customElements.define('ol-book-lists', OlBookLists);
