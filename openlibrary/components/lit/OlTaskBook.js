import { LitElement, html, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { translate } from './utils/labels.js';
import './OlIcon.js';
import './OLButton.js';
import './OlTooltip.js';

export const DEFAULT_LABELS = {
    editionCount: 'one of %(count)s editions of this work',
    viewBook: 'Go to book page',
    editBook: 'Go to edit page'
};

/**
 * A book on the Tasks pages: cover, title, byline and edition line, and
 * under it the book's open tasks as menu-style links.
 *
 * Renders into the **light DOM**: `contribute.css` styles it, the site-wide
 * `data-ol-link-track` listener has to see its links, and contribute.js hides
 * skipped tasks by `data-task-key`. None of that crosses a shadow root. The
 * host is `display: contents`, so its children lay out as if it weren't there.
 * Server-rendered children are placeholders, removed when it upgrades.
 *
 * @element ol-task-book
 *
 * @prop {Object} book - The book, as `build_book_header` returns it.
 * @prop {Array} tasks - Its open tasks, as `build_task_summary` returns them.
 * @prop {Boolean} compact - The small cover, for lists.
 * @prop {String} href - Where the cover and title lead. Default: the book page.
 *     Anywhere else adds view and edit buttons that reach the book.
 * @prop {String} track - The title link's analytics "Category|Action|Label".
 * @prop {String} taskTrack - The task links' analytics "Category|Action"; the field is the label.
 * @prop {Object} labels - Translated overrides for DEFAULT_LABELS (JSON).
 */
export class OlTaskBook extends LitElement {
    static properties = {
        book: { type: Object },
        tasks: { type: Array },
        compact: { type: Boolean },
        href: { type: String },
        track: { type: String },
        taskTrack: { type: String, attribute: 'task-track' },
        labels: { type: Object }
    };

    constructor() {
        super();
        this.book = null;
        this.tasks = [];
        this.compact = false;
        this.href = '';
        this.track = '';
        this.taskTrack = '';
        this.labels = {};
    }

    createRenderRoot() {
        return this;
    }

    connectedCallback() {
        // The server's placeholders go before the first render; a later reconnect keeps what Lit rendered.
        if (!this.hasUpdated) this.replaceChildren();
        super.connectedCallback();
        // Render now rather than a microtask later, so no frame shows it empty.
        if (!this.hasUpdated) this.performUpdate();
    }

    _t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    _cover() {
        if (this.book.cover_url) {
            return html`<img class="contrib-book__cover" src=${this.book.cover_url} alt="" width="60" height="90" loading="lazy" />`;
        }
        return html`<div class="contrib-book__cover contrib-book__cover--empty" aria-hidden="true"><ol-icon name="book-open"></ol-icon></div>`;
    }

    _actions() {
        return html`<div class="contrib-book__actions">
            <ol-tooltip content=${this._t('viewBook')}>
                <ol-button variant="ghost" shape="icon" size="small" href=${this.book.key} aria-label=${this._t('viewBook')}>
                    <ol-icon name="eye" size="sm"></ol-icon>
                </ol-button>
            </ol-tooltip>
            <ol-tooltip content=${this._t('editBook')}>
                <ol-button variant="ghost" shape="icon" size="small" href=${this.book.edit_url} aria-label=${this._t('editBook')}>
                    <ol-icon name="pencil" size="sm"></ol-icon>
                </ol-button>
            </ol-tooltip>
        </div>`;
    }

    _book() {
        const book = this.book;
        const href = this.href || book.key;
        return html`<div class="contrib-book${this.compact ? ' contrib-book--compact' : ''}">
            <a class="contrib-cover-link" href=${href} tabindex="-1" aria-hidden="true">${this._cover()}</a>
            <div class="contrib-book__meta">
                <div class="contrib-book__title">
                    <a href=${href} data-ol-link-track=${ifDefined(this.track || undefined)}>${book.title}</a>
                </div>
                ${book.authors ? html`<div class="contrib-book__authors">${book.authors}</div>` : nothing}
                <div class="contrib-book__line">
                    ${book.edition_line ? html`<span>${book.edition_line}</span>` : nothing} ${book.isbn13 ? html`<span>ISBN ${book.isbn13}</span>` : nothing}
                    ${book.edition_count > 1 ? html`<span>${this._t('editionCount', { count: book.edition_count })}</span>` : nothing}
                </div>
            </div>
            ${href !== book.key ? this._actions() : nothing}
        </div>`;
    }

    _tasks() {
        return html`<ul class="contrib-row__tasks">
            ${this.tasks.map(
                task =>
                    html`<li class="contrib-row__task" data-task-key=${task.key}>
                        <a href=${task.url} data-ol-link-track=${`${this.taskTrack}|${task.field}`}>
                            <span class="contrib-row__badge"><ol-icon name="plus" size="sm"></ol-icon></span>
                            <span>${task.action_label}</span>
                        </a>
                    </li>`
            )}
        </ul>`;
    }

    render() {
        if (!this.book) return nothing;
        return html`${this._book()}${this.tasks?.length ? this._tasks() : nothing}`;
    }
}

customElements.define('ol-task-book', OlTaskBook);
