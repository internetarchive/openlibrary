import { LitElement, html, nothing } from 'lit';
import './OlTaskBook.js';

// While the server builds the list in the background it answers 202: ask again soon, then every few
// seconds, for as long as its Solr query may take, then give up.
const RETRY_MS = [1000, 1000, 2000, 3000, 5000];
const MAX_TRIES = 36;

/**
 * The Tasks dashboard's list: a card per book, each an `ol-task-book` with its open tasks.
 * Its title and cover open the book's first task, since the list is in priority order.
 *
 * Takes the rows inline, or fetches them from `src` (`/tasks/rows.json`) when
 * the page rendered before they were ready. Light DOM, like `ol-task-book`, for
 * the same reasons. Server-rendered children are placeholders: they stay up
 * while it fetches and go when the rows render.
 *
 * @element ol-task-rows
 *
 * @prop {Array} rows - `{book, tasks}` per card, as `build_task_rows` returns them.
 * @prop {String} src - Where to fetch the rows from when `rows` isn't given.
 * @prop {String} titleTrack - The title links' analytics "Category|Action"; the first task's field is the label.
 * @prop {String} taskTrack - The task links' analytics "Category|Action"; the field is the label.
 * @prop {Object} labels - Translated strings, passed down to each `ol-task-book`.
 *
 * @fires ol-task-rows-render - After the rows render. detail: { count: Number }
 * @fires ol-task-rows-error - When `src` errors or runs out of tries.
 */
export class OlTaskRows extends LitElement {
    static properties = {
        rows: { type: Array },
        src: { type: String },
        titleTrack: { type: String, attribute: 'title-track' },
        taskTrack: { type: String, attribute: 'task-track' },
        labels: { type: Object }
    };

    constructor() {
        super();
        this.rows = null;
        this.src = '';
        this.titleTrack = '';
        this.taskTrack = '';
        this.labels = {};
        this._placeholders = null;
    }

    createRenderRoot() {
        return this;
    }

    connectedCallback() {
        this._placeholders ??= [...this.childNodes];
        super.connectedCallback();
        if (!this.hasUpdated) this.performUpdate();
        if (!this.rows && this.src) this._load();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._abort?.abort();
    }

    async _load() {
        this._abort = new AbortController();
        const { signal } = this._abort;
        for (let attempt = 0; attempt < MAX_TRIES; attempt++) {
            try {
                const res = await fetch(this.src, { signal });
                if (res.ok && res.status !== 202) {
                    this.rows = (await res.json()).rows;
                    return;
                }
                if (!res.ok) break;
            } catch (e) {
                if (signal.aborted) return;
                // Offline or a dropped request: try again.
            }
            await new Promise(resolve => setTimeout(resolve, RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)]));
            if (signal.aborted) return;
        }
        this._removePlaceholders();
        this.dispatchEvent(new CustomEvent('ol-task-rows-error', { bubbles: true }));
    }

    _removePlaceholders() {
        this._placeholders?.forEach(node => node.remove());
        this._placeholders = [];
    }

    willUpdate(changed) {
        if (changed.has('rows') && this.rows) this._removePlaceholders();
    }

    updated(changed) {
        if (changed.has('rows') && this.rows) {
            this.dispatchEvent(new CustomEvent('ol-task-rows-render', { bubbles: true, detail: { count: this.rows.length } }));
        }
    }

    render() {
        if (!this.rows) return nothing;
        return html`<ol class="contrib-rows">
            ${this.rows.map(
                row =>
                    html`<li class="contrib-row" data-book-row>
                        <ol-task-book
                            compact
                            .book=${row.book}
                            .tasks=${row.tasks}
                            .labels=${this.labels}
                            href=${row.tasks[0].url}
                            track=${`${this.titleTrack}|${row.tasks[0].field}`}
                            task-track=${this.taskTrack}
                        ></ol-task-book>
                    </li>`
            )}
        </ol>`;
    }
}

customElements.define('ol-task-rows', OlTaskRows);
