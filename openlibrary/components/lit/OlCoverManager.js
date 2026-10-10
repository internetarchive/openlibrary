import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';

import './OLButton.js';
import './OlIcon.js';
import { showToast } from './OlToastRegion.js';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';
import { translate } from './utils/labels.js';

export const DEFAULT_LABELS = {
    intro: 'Choose the image to show as the cover, or add a new one.',
    images: 'Images',
    addImage: 'Add image',
    addHint: 'Drop a file, paste, or browse',
    dropHere: 'Drop the image to upload it',
    current: 'Current',
    sourceArchive: 'Internet Archive',
    sourceWikidata: 'Wikidata',
    sourceEdition: 'Edition',
    sourceUpload: 'Uploaded',
    detailScanCover: 'Scan · cover page',
    detailScanTitle: 'Scan · title page',
    detailWikidata: 'Wikimedia Commons',
    detailEdition: 'Cover of an edition',
    detailUploadBy: '%(name)s · %(date)s',
    detailYou: 'You · just now',
    pickLabelCurrent: '%(name)s (current cover)',
    remove: 'Remove',
    removeLabel: 'Remove %(name)s',
    undo: 'Undo',
    undoLabel: 'Keep %(name)s',
    uploading: 'Uploading…',
    statusIdle: 'Removed images can be restored from the edit history.',
    statusSelect: 'When you save, the selected image becomes the cover.',
    statusAdd: { one: '%(count)s new image will be added.', other: '%(count)s new images will be added.' },
    statusRemove: { one: '%(count)s image will be removed.', other: '%(count)s images will be removed.' },
    guidelines: 'Cover guidelines',
    cancel: 'Cancel',
    save: 'Save',
    saved: 'Cover updated',
    loading: 'Loading images…',
    errorLoad: 'The images couldn’t be loaded.',
    retry: 'Try again',
    errorType: 'Choose a JPG, GIF, PNG or WebP image.',
    errorSize: 'Images must be 10 MB or smaller.',
    errorUpload: 'That image couldn’t be uploaded.',
    errorSave: 'Your changes couldn’t be saved. Try again.',
};

const ACCEPT = '.jpg,.jpeg,.gif,.png,.webp,image/jpeg,image/gif,image/png,image/webp';
const IMAGE_TYPES = ['image/jpeg', 'image/gif', 'image/png', 'image/webp'];
const MAX_BYTES = 10 * 1024 * 1024;

/**
 * Picks and manages the images for a book, work, or author: every image
 * attached to it, plus suggestions that are always listed (Internet Archive
 * scans, a Wikidata photo, a work's edition covers). One is selected as the
 * cover; new images are added by drop, paste, or file picker; uploaded images
 * can be removed from the record. Nothing is saved until Save.
 *
 * Lives inside an `<ol-dialog>`: it loads when the dialog opens, listens for
 * pasted images while open, and closes the dialog on Save or Cancel.
 *
 * @element ol-cover-manager
 *
 * @prop {String} docKey - The record whose images are managed, e.g. `/books/OL1M`.
 *     Attribute: `doc-key`.
 * @prop {String} guidelinesUrl - Link shown in the footer. Attribute: `guidelines-url`.
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS.
 *
 * @fires ol-cover-manager-save - The cover was saved. detail: { coverId: Number|null, thumb: String|null, large: String|null }
 */
export class OlCoverManager extends LitElement {
    static properties = {
        docKey: { type: String, attribute: 'doc-key' },
        guidelinesUrl: { type: String, attribute: 'guidelines-url' },
        labels: { type: Object },
        _data: { state: true },
        _loadState: { state: true },
        _selected: { state: true },
        _removed: { state: true },
        _added: { state: true },
        _hidden: { state: true },
        _saving: { state: true },
        _dragging: { state: true },
        _error: { state: true },
    };

    static styles = css`
        :host {
            display: block;
            font-family: var(--font-family-body);
            color: var(--color-text);
            text-align: start;
        }

        .intro {
            margin: 0 0 var(--spacing-lg);
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-body);
        }

        .grid-wrap {
            position: relative;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(124px, 1fr));
            gap: var(--spacing-lg);
            margin: 0;
            padding: 0;
            list-style: none;
        }

        .tile {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-xs);
            min-width: 0;
        }

        .pick,
        .add {
            position: relative;
            display: block;
            width: 100%;
            aspect-ratio: 2 / 3;
            padding: var(--spacing-2xs);
            border: var(--border-width-thin) solid transparent;
            border-radius: var(--border-radius-card);
            background: transparent;
            cursor: pointer;
            min-height: 0;
            box-sizing: border-box;
            font: inherit;
            color: inherit;
            transition: transform var(--duration-press) var(--ease-state);
        }

        .pick:active:not(:disabled),
        .add:active {
            transform: scale(var(--press-scale));
        }

        .pick:focus-visible,
        .add:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .pick[aria-pressed='true'] {
            border-color: var(--color-primary);
            background: var(--color-primary-subtle);
            box-shadow: 0 0 0 var(--border-width-thick) var(--color-primary);
        }

        .pick:disabled {
            cursor: default;
        }

        /* Covers sit on a shared baseline so the captions below line up. */
        .frame {
            display: grid;
            place-items: end center;
            width: 100%;
            height: 100%;
            overflow: hidden;
            border-radius: var(--border-radius-thumbnail);
        }

        .frame img {
            display: block;
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            box-shadow: var(--box-shadow-raised);
        }

        .removed .frame img {
            opacity: 0.3;
        }

        .badge {
            position: absolute;
            top: var(--spacing-sm);
            inset-inline-start: var(--spacing-sm);
            padding: var(--spacing-3xs) var(--spacing-xs);
            border-radius: var(--border-radius-badge);
            background: var(--color-surface-inverse);
            color: var(--color-text-inverse);
            font-size: var(--font-size-label-small);
            font-weight: var(--font-weight-semibold);
            line-height: var(--line-height-single);
        }

        .check {
            position: absolute;
            top: var(--spacing-xs);
            inset-inline-end: var(--spacing-xs);
            display: grid;
            place-items: center;
            width: 24px;
            height: 24px;
            border-radius: var(--border-radius-circle);
            background: var(--color-primary);
            color: var(--color-on-primary);
        }

        .busy {
            position: absolute;
            inset: var(--spacing-2xs);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: var(--spacing-xs);
            border-radius: var(--border-radius-thumbnail);
            background: color-mix(in srgb, var(--color-surface) 80%, transparent);
            font-size: var(--font-size-label-medium);
            font-weight: var(--font-weight-medium);
        }

        .busy ol-icon {
            animation: spin var(--duration-spin) linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .meta {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: var(--spacing-3xs);
            padding-inline: var(--spacing-2xs);
            text-align: center;
            font-size: var(--font-size-label-medium);
            line-height: var(--line-height-meta);
            color: var(--color-text-secondary);
            overflow-wrap: anywhere;
        }

        .source {
            padding: var(--spacing-3xs) var(--spacing-xs);
            border-radius: var(--border-radius-badge);
            font-size: var(--font-size-label-small);
            font-weight: var(--font-weight-semibold);
            line-height: var(--line-height-single);
            background: var(--color-surface-sunken);
            color: var(--color-text);
        }

        .source.suggested {
            background: var(--color-info-bg);
            color: var(--color-info-fg);
        }

        /* Remove / Undo: quiet text links, so they sit on a caption line like the detail row. */
        .text-action {
            padding: 0;
            border: 0;
            background: none;
            color: var(--color-text-secondary);
            font: inherit;
            text-decoration: underline;
            text-underline-offset: 2px;
            cursor: pointer;
        }

        .text-action.danger {
            color: var(--color-error-fg);
        }

        .text-action:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
            border-radius: var(--border-radius-sm);
        }

        .add {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: var(--spacing-xs);
            padding: var(--spacing-md);
            border: var(--border-width-thick) dashed var(--color-border);
            background: var(--color-surface-raised);
            color: var(--color-text-secondary);
            text-align: center;
            font-size: var(--font-size-label-medium);
            line-height: var(--line-height-meta);
        }

        .add strong {
            color: var(--color-text);
            font-size: var(--font-size-label-large);
            font-weight: var(--font-weight-semibold);
        }

        @media (hover: hover) and (pointer: fine) {
            .pick:hover:not(:disabled):not([aria-pressed='true']) {
                background: var(--color-hover-overlay);
            }

            .text-action:hover {
                text-decoration-thickness: 2px;
            }

            .text-action:not(.danger):hover {
                color: var(--color-text);
            }

            .add:hover {
                border-color: var(--color-primary);
                background: var(--color-primary-subtle);
                color: var(--color-primary);
            }

            .add:hover strong {
                color: var(--color-primary);
            }
        }

        .drop-target {
            position: absolute;
            inset: calc(-1 * var(--spacing-sm));
            display: grid;
            place-items: center;
            border: var(--border-width-thick) dashed var(--color-primary);
            border-radius: var(--border-radius-card);
            background: color-mix(in srgb, var(--color-primary-subtle) 92%, transparent);
            color: var(--color-primary);
            font-size: var(--font-size-title-small);
            font-weight: var(--font-weight-semibold);
            pointer-events: none;
        }

        .error {
            display: flex;
            align-items: center;
            gap: var(--spacing-xs);
            margin: var(--spacing-lg) 0 0;
            padding: var(--spacing-sm) var(--spacing-md);
            border: var(--border-width-thin) solid var(--color-error-border);
            border-radius: var(--border-radius-notification);
            background: var(--color-error-bg);
            color: var(--color-error-fg);
            font-size: var(--font-size-body-small);
        }

        .footer {
            position: sticky;
            bottom: calc(-1 * var(--ol-dialog-padding, 0px));
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: var(--spacing-md);
            margin: var(--spacing-xl) calc(-1 * var(--ol-dialog-padding, 0px)) calc(-1 * var(--ol-dialog-padding, 0px));
            padding: var(--spacing-lg) var(--ol-dialog-padding, 0px);
            border-top: var(--border-divider);
            background: var(--color-surface);
        }

        .status {
            flex: 1 1 260px;
            margin: 0;
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-body);
        }

        .status a {
            color: var(--color-link);
        }

        .actions {
            display: flex;
            gap: var(--spacing-sm);
            margin-inline-start: auto;
        }

        .skeleton .frame {
            background: var(--color-surface-sunken);
            animation: pulse var(--duration-slower) var(--ease-in-out-cubic) infinite alternate;
        }

        @keyframes pulse {
            to { opacity: 0.5; }
        }

        @media (prefers-reduced-motion: reduce) {
            .skeleton .frame,
            .busy ol-icon {
                animation: none;
            }
        }

        .visually-hidden {
            position: absolute;
            width: 1px;
            height: 1px;
            overflow: hidden;
            clip-path: inset(50%);
            white-space: nowrap;
        }
    `;

    constructor() {
        super();
        this.docKey = '';
        this.guidelinesUrl = '/help/faq/editing#picture';
        this.labels = {};
        this._data = null;
        this._loadState = 'idle';
        this._selected = null;
        this._removed = new Set();
        this._added = [];
        this._hidden = new Set();
        this._saving = false;
        this._dragging = false;
        this._error = '';
        this._dragDepth = 0;
        this._pendingCount = 0;
        this._dialog = null;
        this._onOpen = () => this.load();
        this._onClosed = () => this._reset();
        this._onPaste = (e) => this._handlePaste(e);
    }

    connectedCallback() {
        super.connectedCallback();
        this._dialog = this.closest('ol-dialog');
        if (this._dialog) {
            this._dialog.addEventListener('ol-open', this._onOpen);
            this._dialog.addEventListener('ol-after-close', this._onClosed);
            if (this._dialog.open) this.load();
        } else {
            this.load();
        }
        document.addEventListener('paste', this._onPaste);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._dialog?.removeEventListener('ol-open', this._onOpen);
        this._dialog?.removeEventListener('ol-after-close', this._onClosed);
        document.removeEventListener('paste', this._onPaste);
        this._reset();
    }

    _t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    get _endpoint() {
        return this.docKey.startsWith('/authors/') ? `${this.docKey}/photos` : `${this.docKey}/covers`;
    }

    /** Fetch the record's images and start a fresh session. */
    async load() {
        if (!this.docKey) return;
        this._reset();
        this._loadState = 'loading';
        try {
            const response = await fetch(`${this._endpoint}.json`, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
            if (!response.ok) throw new Error(response.statusText);
            this._data = await response.json();
            this._selected = this._data.current;
            this._loadState = 'ready';
        } catch {
            this._loadState = 'error';
        }
    }

    _reset() {
        for (const item of this._added) {
            if (item.objectUrl) URL.revokeObjectURL(item.objectUrl);
        }
        this._added = [];
        this._removed = new Set();
        this._hidden = new Set();
        this._error = '';
        this._saving = false;
        this._dragging = false;
        this._dragDepth = 0;
    }

    /** Session uploads first, after the suggestions; then what the record already has. */
    get _items() {
        const items = this._data?.items ?? [];
        const suggested = items.filter((item) => item.kind !== 'upload');
        const uploads = items.filter((item) => item.kind === 'upload');
        return [...suggested, ...this._added, ...uploads].filter((item) => !this._hidden.has(item.id));
    }

    get _uploadedIds() {
        return this._added.filter((item) => !item.pending && !this._removed.has(item.image_id)).map((item) => item.image_id);
    }

    get _isDirty() {
        return Boolean(this._data) && (this._selected !== this._data.current || this._removed.size > 0 || this._uploadedIds.length > 0);
    }

    _isOpen() {
        return this._dialog ? this._dialog.open : this.isConnected;
    }

    // Adding images

    _openPicker() {
        this.shadowRoot.querySelector('input[type="file"]')?.click();
    }

    _onFileInput(e) {
        this._addFiles([...e.target.files]);
        e.target.value = '';
    }

    _handlePaste(e) {
        if (!this._isOpen() || this._loadState !== 'ready') return;
        const files = [...(e.clipboardData?.files ?? [])].filter((file) => file.type.startsWith('image/'));
        if (!files.length) return;
        e.preventDefault();
        this._addFiles(files);
    }

    _hasFiles(e) {
        return [...(e.dataTransfer?.types ?? [])].includes('Files');
    }

    _onDragEnter(e) {
        if (!this._hasFiles(e) || this._loadState !== 'ready') return;
        e.preventDefault();
        this._dragDepth += 1;
        this._dragging = true;
    }

    _onDragOver(e) {
        if (!this._hasFiles(e) || this._loadState !== 'ready') return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    }

    _onDragLeave(e) {
        if (!this._hasFiles(e)) return;
        this._dragDepth = Math.max(0, this._dragDepth - 1);
        if (this._dragDepth === 0) this._dragging = false;
    }

    _onDrop(e) {
        if (!this._hasFiles(e) || this._loadState !== 'ready') return;
        e.preventDefault();
        this._dragDepth = 0;
        this._dragging = false;
        this._addFiles([...e.dataTransfer.files]);
    }

    _addFiles(files) {
        this._error = '';
        for (const file of files) {
            if (!IMAGE_TYPES.includes(file.type)) {
                this._error = this._t('errorType');
                continue;
            }
            if (file.size > MAX_BYTES) {
                this._error = this._t('errorSize');
                continue;
            }
            this._upload(file);
        }
    }

    async _upload(file) {
        this._pendingCount += 1;
        const objectUrl = URL.createObjectURL(file);
        const placeholder = { id: `pending:${this._pendingCount}`, kind: 'upload', pending: true, thumb: objectUrl, objectUrl, removable: false };
        this._added = [placeholder, ...this._added];

        const body = new FormData();
        // Send a neutral name: the firewall rejects some real ones (apostrophes, #13286), and the server only checks the extension.
        body.append('file', file, `image.${file.type === 'image/jpeg' ? 'jpg' : file.type.split('/')[1]}`);
        try {
            const response = await fetch(`${this._endpoint}/upload.json`, { method: 'POST', body, credentials: 'same-origin' });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.detail || response.statusText);
            // Keep showing the local preview: the coverstore may still be making its thumbnails.
            const item = { ...result, thumb: objectUrl, objectUrl, session: true };
            this._added = this._added.map((added) => (added.id === placeholder.id ? item : added));
            this._selected = item.id;
        } catch {
            URL.revokeObjectURL(objectUrl);
            this._added = this._added.filter((added) => added.id !== placeholder.id);
            this._error = this._t('errorUpload');
        }
    }

    // Choosing and removing

    _select(item) {
        if (item.pending || this._removed.has(item.image_id)) return;
        this._selected = item.id;
    }

    _remove(item) {
        this._removed = new Set(this._removed).add(item.image_id);
    }

    _undoRemove(item) {
        const removed = new Set(this._removed);
        removed.delete(item.image_id);
        this._removed = removed;
    }

    _hide(item) {
        // A scan page that doesn't exist (many items have no title page) 404s; drop its tile.
        if (item.kind === 'upload' || item.id === this._selected) return;
        this._hidden = new Set(this._hidden).add(item.id);
    }

    _onGridKeydown(e) {
        const picks = [...this.shadowRoot.querySelectorAll('.pick')];
        const current = picks.indexOf(this.shadowRoot.activeElement);
        if (current === -1) return;
        const rtl = getComputedStyle(this).direction === 'rtl';
        const key = rtl && e.key === 'ArrowLeft' ? 'ArrowRight' : rtl && e.key === 'ArrowRight' ? 'ArrowLeft' : e.key;
        const next = getNextKeyboardFocusIndex(key, { count: picks.length, current, orientation: 'horizontal', wrap: false, isDisabled: (i) => picks[i].disabled });
        if (next === -1) return;
        e.preventDefault();
        picks[next].focus();
    }

    // Saving

    async _save() {
        if (!this._isDirty || this._saving) return;
        this._saving = true;
        this._error = '';
        try {
            const response = await fetch(`${this._endpoint}.json`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ selected: this._selected, added: this._uploadedIds, removed: [...this._removed] }),
            });
            if (!response.ok) throw new Error(response.statusText);
            const { cover_id: coverId, state } = await response.json();
            const cover = state.items.find((item) => item.image_id === coverId);
            this.dispatchEvent(new CustomEvent('ol-cover-manager-save', {
                detail: { coverId, thumb: cover?.thumb ?? null, large: cover?.large ?? null },
                bubbles: true,
                composed: true,
            }));
            this._dialog?.close('saved');
            showToast(this._t('saved'), { type: 'success' });
        } catch {
            this._error = this._t('errorSave');
        } finally {
            this._saving = false;
        }
    }

    _cancel() {
        if (this._dialog) this._dialog.close();
        else this.load();
    }

    // Rendering

    _describe(item) {
        const date = item.created ? new Intl.DateTimeFormat(document.documentElement.lang || 'en', { month: 'short', year: 'numeric' }).format(new Date(item.created)) : '';
        switch (item.kind) {
        case 'archive_cover': return { source: this._t('sourceArchive'), detail: this._t('detailScanCover'), suggested: true };
        case 'archive_title': return { source: this._t('sourceArchive'), detail: this._t('detailScanTitle'), suggested: true };
        case 'wikidata': return { source: this._t('sourceWikidata'), detail: this._t('detailWikidata'), suggested: true };
        case 'edition': return { source: this._t('sourceEdition'), detail: this._t('detailEdition'), suggested: true };
        default: {
            let detail = date;
            if (item.session) detail = this._t('detailYou');
            else if (item.added_by && date) detail = this._t('detailUploadBy', { name: item.added_by.name, date });
            else if (item.added_by) detail = item.added_by.name;
            return { source: this._t('sourceUpload'), detail, suggested: false };
        }
        }
    }

    _renderTile(item) {
        const { source, detail, suggested } = this._describe(item);
        const name = detail ? `${source}, ${detail}` : source;
        const selected = item.id === this._selected;
        const isCurrent = item.id === this._data.current;
        const removed = this._removed.has(item.image_id);
        // The current cover can go once another image is picked to replace it.
        const canRemove = item.removable && !item.pending && !selected;
        const label = isCurrent ? this._t('pickLabelCurrent', { name }) : name;

        return html`<li class="tile ${removed ? 'removed' : ''}">
            <button
                class="pick"
                type="button"
                aria-pressed=${selected ? 'true' : 'false'}
                aria-label=${label}
                ?disabled=${removed || item.pending}
                @click=${() => this._select(item)}
            >
                <span class="frame"><img src=${item.thumb} alt="" loading="lazy" @error=${() => this._hide(item)}></span>
                ${isCurrent ? html`<span class="badge" aria-hidden="true">${this._t('current')}</span>` : nothing}
                ${selected ? html`<span class="check" aria-hidden="true"><ol-icon name="check" size="sm"></ol-icon></span>` : nothing}
                ${item.pending ? html`<span class="busy"><ol-icon name="loader"></ol-icon>${this._t('uploading')}</span>` : nothing}
            </button>
            <div class="meta">
                <span class="source ${suggested ? 'suggested' : ''}">${source}</span>
                ${detail ? html`<span>${detail}</span>` : nothing}
                ${canRemove && !removed ? html`<button type="button" class="text-action danger" aria-label=${this._t('removeLabel', { name })} @click=${() => this._remove(item)}>${this._t('remove')}</button>` : nothing}
                ${removed ? html`<button type="button" class="text-action" aria-label=${this._t('undoLabel', { name })} @click=${() => this._undoRemove(item)}>${this._t('undo')}</button>` : nothing}
            </div>
        </li>`;
    }

    _renderStatus() {
        if (this._added.some((item) => item.pending)) return this._t('uploading');
        if (!this._isDirty) {
            return html`${this._t('statusIdle')} <a href=${this.guidelinesUrl} target="_blank" rel="noopener">${this._t('guidelines')}</a>`;
        }
        const parts = [];
        if (this._selected !== this._data.current) parts.push(this._t('statusSelect'));
        const newUploads = this._uploadedIds.filter((id) => `img:${id}` !== this._selected).length;
        if (newUploads) parts.push(this._t('statusAdd', { count: newUploads }));
        if (this._removed.size) parts.push(this._t('statusRemove', { count: this._removed.size }));
        return parts.join(' ');
    }

    render() {
        if (this._loadState === 'error') {
            return html`<div class="error" role="alert">
                <ol-icon name="circle-alert" size="sm"></ol-icon>
                <span>${this._t('errorLoad')}</span>
                <ol-button variant="secondary" size="small" @click=${() => this.load()}>${this._t('retry')}</ol-button>
            </div>`;
        }

        if (this._loadState !== 'ready') {
            return html`<p class="intro">${this._t('intro')}</p>
                <ul class="grid skeleton" aria-busy="true" aria-label=${this._t('loading')}>${[0, 1, 2, 3].map(() => html`<li class="tile"><span class="pick"><span class="frame"></span></span></li>`)}</ul>`;
        }

        const pending = this._added.some((item) => item.pending);
        return html`
            <p class="intro">${this._t('intro')}</p>
            <div
                class="grid-wrap"
                @dragenter=${this._onDragEnter}
                @dragover=${this._onDragOver}
                @dragleave=${this._onDragLeave}
                @drop=${this._onDrop}
            >
                <ul class="grid" aria-label=${this._t('images')} @keydown=${this._onGridKeydown}><li class="tile">
                        <button class="add" type="button" @click=${this._openPicker}>
                            <ol-icon name="upload" size="lg"></ol-icon>
                            <strong>${this._t('addImage')}</strong>
                            <span>${this._t('addHint')}</span>
                        </button>
                        <input class="visually-hidden" type="file" accept=${ACCEPT} multiple tabindex="-1" aria-hidden="true" @change=${this._onFileInput}>
                    </li>${repeat(this._items, (item) => item.id, (item) => this._renderTile(item))}</ul>
                ${this._dragging ? html`<div class="drop-target">${this._t('dropHere')}</div>` : nothing}
            </div>
            ${this._error ? html`<p class="error" role="alert"><ol-icon name="circle-alert" size="sm"></ol-icon>${this._error}</p>` : nothing}
            <div class="footer">
                <p class="status" aria-live="polite">${this._renderStatus()}</p>
                <div class="actions">
                    <ol-button variant="secondary" @click=${this._cancel}>${this._t('cancel')}</ol-button>
                    <ol-button variant="primary" ?disabled=${!this._isDirty || pending} ?loading=${this._saving} @click=${this._save}>${this._t('save')}</ol-button>
                </div>
            </div>
        `;
    }
}

customElements.define('ol-cover-manager', OlCoverManager);
