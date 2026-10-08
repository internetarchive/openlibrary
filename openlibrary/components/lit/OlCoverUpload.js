import { LitElement, html, css, nothing } from 'lit';
// Registers <ol-button> for the upload / paste actions.
import './OLButton.js';
import './OlIcon.js';
import { translate } from './utils/labels.js';

/**
 * English defaults for every string. Keys must match the `labels` object
 * rendered by `openlibrary/templates/covers/change.html`.
 */
export const DEFAULT_LABELS = {
    introCover: 'There are a few ways to put a cover image on Open Library.',
    introPhoto: 'There are two ways to put an author\'s image on Open Library.',
    learnMore: 'Learn more by reading our',
    guidelinesCover: 'Cover Guidelines',
    guidelinesPhoto: 'Image Guidelines',
    chooseFile: 'Choose a JPG, GIF, PNG or WebP on your computer',
    useImageFrom: 'Or, use an image from %(source)s',
    uploadImage: 'Upload Image',
    pasteLabel: 'Or, paste an image from your clipboard',
    paste: 'Paste Image',
    changeImage: 'Change Image',
    pasteAria: 'Paste image from clipboard',
    previewAlt: 'Selected image preview',
    removeImage: 'Remove image',
    upload: 'Upload',
    uploading: 'Uploading…',
    saved: 'Saved!',
    savedAlt: 'New book cover',
    addAnother: 'Add another image',
    finished: 'Finished',
    noFile: 'Please choose an image first.',
    uploadFailed: 'Could not upload the image. Please try again.',
    noClipboardImage: 'No image found in clipboard',
};

/**
 * The Add-image half of the cover editor: choose or paste an image and upload
 * it to the existing server endpoint, then refresh the page's cover in place.
 *
 * Replaces the old `covers/add.html` iframe. The POST target is the existing
 * `…/add-cover` / `…/add-photo` route (a multipart form handler); the server
 * owns validation and the coverstore upload. The HTML response is only read
 * for its `data-image-id`, which is all this component needs to update the
 * cover the user is looking at.
 *
 * @element ol-cover-upload
 *
 * @prop {String} action - POST target, e.g. `/books/OL1M/add-cover`
 * @prop {String} docType - `/type/work`, `/type/edition`, or `/type/author`
 * @prop {String} coverSelector - CSS selector for the page's cover `<img>`
 * @prop {String} coverstoreUrl - Public coverstore base URL
 * @prop {String} accept - File input `accept` list
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-cover-upload - A new cover was saved. detail: { id: Number }
 */
export class OlCoverUpload extends LitElement {
    static properties = {
        action: { type: String },
        docType: { type: String, attribute: 'doc-type' },
        coverSelector: { type: String, attribute: 'cover-selector' },
        coverstoreUrl: { type: String, attribute: 'coverstore-url' },
        accept: { type: String },
        labels: { type: Object },
        candidates: { type: Array },
        _file: { state: true },
        _previewUrl: { state: true },
        _busy: { state: true },
        _error: { state: true },
        _pasted: { state: true },
        _savedId: { state: true },
        _savedUrl: { state: true },
    };

    static styles = css`
        :host {
            display: block;
            text-align: left;
            font-family: var(--font-family-body);
            color: var(--color-text);
        }

        .intro {
            margin: 0 0 var(--spacing-lg);
            line-height: var(--line-height-body);
        }

        .intro a {
            color: var(--color-link);
        }

        /* The form panel: the same soft card the old server-rendered
           cover form used (legacy form styling), rebuilt from tokens. */
        .panel {
            padding: var(--spacing-sm);
            margin-bottom: var(--spacing-sm);
            background: var(--neutral-100);
            border-radius: var(--border-radius-lg);
        }

        .heading {
            margin: 0 0 var(--spacing-2xs);
            font-size: var(--font-size-body-large);
            font-weight: var(--font-weight-semibold);
            line-height: var(--line-height-heading);
        }

        .row {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--spacing-sm);
        }

        .file {
            flex: 1 1 12rem;
            min-width: 0;
            font: inherit;
        }

        .preview-wrap {
            position: relative;
            display: inline-block;
            margin-top: var(--spacing-sm);
        }

        .preview {
            display: block;
            max-width: 200px;
            max-height: 200px;
            border: var(--border-width) solid var(--color-control-border);
            border-radius: var(--border-radius-thumbnail);
        }

        /* Floating remove control over the chosen/pasted image. */
        .preview-clear {
            position: absolute;
            top: var(--spacing-2xs);
            right: var(--spacing-2xs);
        }

        .candidates {
            display: flex;
            flex-wrap: wrap;
            gap: var(--spacing-sm);
        }

        .candidate {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: var(--spacing-2xs);
        }

        .candidate__img {
            height: 120px;
            width: auto;
            border: var(--border-width) solid var(--color-control-border);
            border-radius: var(--border-radius-thumbnail);
        }

        .status {
            margin: var(--spacing-sm) 0 0;
            line-height: var(--line-height-body);
        }

        .status--error {
            color: var(--color-error-fg);
        }

        .saved {
            text-align: center;
        }

        .saved__img {
            display: block;
            max-width: 200px;
            margin: 0 auto var(--spacing-md);
            border-radius: var(--border-radius-thumbnail);
        }

        .saved__msg {
            margin: 0 0 var(--spacing-lg);
            font-size: var(--font-size-title-medium);
            font-weight: 600;
        }

        .actions {
            display: flex;
            justify-content: center;
            gap: var(--spacing-sm);
        }
    `;

    constructor() {
        super();
        this.action = '';
        this.docType = '';
        this.coverSelector = '.bookCover img';
        this.coverstoreUrl = '';
        this.accept = '.jpg,.jpeg,.gif,.png,.webp';
        this.labels = {};
        this.candidates = [];
        this._file = null;
        this._previewUrl = '';
        this._busy = false;
        this._error = '';
        this._pasted = false;
        this._savedId = null;
        this._savedUrl = '';
        this._onPasteEvent = this._onPasteEvent.bind(this);
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    get _isPhoto() {
        return this.docType === '/type/author';
    }

    /** @returns {HTMLInputElement|null} */
    get _fileInput() {
        return this.renderRoot?.querySelector('input[type="file"]');
    }

    connectedCallback() {
        super.connectedCallback();
        // Cmd/Ctrl+V anywhere while the dialog is open hands us the image
        // directly, with no clipboard permission prompt (unlike the button).
        document.addEventListener('paste', this._onPasteEvent);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('paste', this._onPasteEvent);
        this._revokePreview();
    }

    /** Restore the initial "choose an image" state. Safe to call externally. */
    reset() {
        this._revokePreview();
        this._file = null;
        this._previewUrl = '';
        this._error = '';
        this._pasted = false;
        this._savedId = null;
        this._savedUrl = '';
        const input = this._fileInput;
        if (input) input.value = '';
    }

    _revokePreview() {
        if (this._previewUrl) URL.revokeObjectURL(this._previewUrl);
    }

    /** Discard the chosen/pasted image and return to the empty form. */
    _clearImage() {
        this._revokePreview();
        this._file = null;
        this._previewUrl = '';
        this._pasted = false;
        this._error = '';
        const input = this._fileInput;
        if (input) input.value = '';
    }

    _showPreview(file) {
        this._revokePreview();
        this._previewUrl = URL.createObjectURL(file);
    }

    _onFileChange(event) {
        const file = event.target.files?.[0];
        this._error = '';
        if (file) {
            this._pasted = false;
            this._file = file;
            this._showPreview(file);
        }
    }

    /** Record an image as the pending "pasted" upload and preview it. */
    _setPastedFile(file) {
        this._error = '';
        this._pasted = true;
        this._file = file;
        this._showPreview(file);
    }

    /**
     * Native paste (Cmd/Ctrl+V). `event.clipboardData` carries the image with
     * no permission prompt, so this is the primary paste path; the button's
     * `navigator.clipboard.read()` is the fallback for explicit clicks.
     */
    _onPasteEvent(event) {
        const dialog = this.closest('ol-dialog');
        if (dialog && !dialog.open) return;
        const items = event.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
            if (item.kind !== 'file' || !item.type.startsWith('image/')) continue;
            const file = item.getAsFile();
            if (!file) return;
            event.preventDefault();
            this._setPastedFile(file);
            return;
        }
    }

    async _onPaste() {
        this._error = '';
        try {
            const items = await navigator.clipboard.read();
            for (const item of items) {
                const mimeType = ['image/png', 'image/jpeg', 'image/jpg'].find((type) => item.types.includes(type));
                if (!mimeType) continue;
                const blob = await item.getType(mimeType);
                const extension = mimeType === 'image/png' ? 'png' : mimeType === 'image/jpeg' ? 'jpeg' : 'jpg';
                this._setPastedFile(new File([blob], `pasted-image.${extension}`, { type: mimeType }));
                return;
            }
            this._error = this.t('noClipboardImage');
        } catch {
            // Permission denied or unsupported; the user can still choose a file.
            this._error = this.t('noClipboardImage');
        }
    }

    /** Upload one of the server-supplied external image URLs (by URL, no file). */
    async _useUrl(url) {
        const data = new FormData();
        data.append('url', url);
        await this._post(data);
    }

    async _onSubmit() {
        const file = this._file;
        if (!file) {
            this._error = this.t('noFile');
            return;
        }
        const data = new FormData();
        data.append('file', file, file.name);
        await this._post(data);
    }

    async _post(data) {
        this._busy = true;
        this._error = '';
        try {
            const response = await fetch(this.action, {
                method: 'POST',
                body: data,
                credentials: 'same-origin',
            });
            const markup = await response.text();
            const id = response.ok ? this._extractCoverId(markup) : null;
            if (!id) {
                this._error = this.t('uploadFailed');
                return;
            }
            this._applyCover(id);
            this._savedId = id;
            this._savedUrl = this._coverUrl(id);
            this.dispatchEvent(
                new CustomEvent('ol-cover-upload', {
                    bubbles: true,
                    composed: true,
                    detail: { id },
                }),
            );
        } catch {
            this._error = this.t('uploadFailed');
        } finally {
            this._busy = false;
        }
    }

    /**
     * The saved template carries the new cover's id on its `imageSaved` element.
     * @param {String} markup
     * @returns {Number|null}
     */
    _extractCoverId(markup) {
        const doc = new DOMParser().parseFromString(markup, 'text/html');
        const value = doc.querySelector('[data-image-id]')?.getAttribute('data-image-id');
        return value && /^\d+$/.test(value) ? Number(value) : null;
    }

    _coverUrl(id) {
        const category = this._isPhoto ? 'a' : 'b';
        return `${this.coverstoreUrl}/${category}/id/${id}-M.jpg`;
    }

    /**
     * Update the cover the user sees. Mirrors the old `initCoversSaved` handler,
     * which reached into the parent document from the iframe; now it is the
     * same document, so a plain querySelector + display toggle does it.
     * @param {Number} id
     */
    _applyCover(id) {
        const img = document.querySelector(this.coverSelector);
        if (!img) return;
        const url = this._coverUrl(id);
        img.setAttribute('src', url);
        if (this._isPhoto) return;
        // Book covers sit over a generated blank panel; swap which one shows.
        img.setAttribute('srcset', url);
        const cover = img.closest('div');
        if (cover) {
            cover.style.display = 'block';
            const blank = cover.nextElementSibling;
            if (blank) blank.style.display = 'none';
        }
    }

    _onAddAnother() {
        this.reset();
    }

    _onFinished() {
        this.closest('ol-dialog')?.close('finished');
    }

    render() {
        return this._savedId ? this._renderSaved() : this._renderForm();
    }

    _renderSaved() {
        return html`
            <div class="saved">
                <img class="saved__img" src=${this._savedUrl} alt=${this.t('savedAlt')} />
                <p class="saved__msg" role="status">${this.t('saved')}</p>
                <div class="actions">
                    <ol-button class="add-another" @click=${this._onAddAnother}>${this.t('addAnother')}</ol-button>
                    <ol-button class="finished" variant="primary" @click=${this._onFinished}>${this.t('finished')}</ol-button>
                </div>
            </div>
        `;
    }

    _renderPreview() {
        if (!this._previewUrl) return nothing;
        return html`
            <div class="preview-wrap">
                <img class="preview" src=${this._previewUrl} alt=${this.t('previewAlt')} />
                <ol-button
                    class="preview-clear"
                    shape="icon"
                    variant="ghost"
                    aria-label=${this.t('removeImage')}
                    @click=${this._clearImage}
                >
                    <ol-icon name="x"></ol-icon>
                </ol-button>
            </div>
        `;
    }

    /** Server-supplied remote images (Wikidata, Internet Archive), grouped by source. */
    _renderCandidates() {
        const groups = new Map();
        for (const candidate of this.candidates ?? []) {
            if (!candidate?.url) continue;
            const source = candidate.source ?? '';
            if (!groups.has(source)) groups.set(source, []);
            groups.get(source).push(candidate.url);
        }
        return [...groups.entries()].map(
            ([source, urls]) => html`
                <div class="panel">
                    <h3 class="heading">${this.t('useImageFrom', { source })}</h3>
                    <div class="candidates">
                        ${urls.map(
        (url) => html`
                                <div class="candidate">
                                    <img class="candidate__img" src=${url} alt="" />
                                    <ol-button class="candidate__use" @click=${() => this._useUrl(url)}
                                        >${this.t('uploadImage')}</ol-button
                                    >
                                </div>
                            `,
    )}
                    </div>
                </div>
            `,
        );
    }

    _renderForm() {
        const intro = this.t(this._isPhoto ? 'introPhoto' : 'introCover');
        const guideline = this.t(this._isPhoto ? 'guidelinesPhoto' : 'guidelinesCover');
        const upload = html`<ol-button
            class="upload-button"
            variant="primary"
            ?loading=${this._busy}
            ?disabled=${this._busy}
            @click=${this._onSubmit}
        >${this.t('upload')}</ol-button>`;
        return html`
            <p class="intro">
                ${intro}
                ${' '}
                ${this.t('learnMore')}
                <a href="/help/faq/editing#picture" target="_blank" rel="noopener noreferrer">${guideline}</a>.
            </p>

            <div class="panel">
                <h3 class="heading">${this.t('chooseFile')}</h3>
                <div class="row">
                    <input
                        class="file"
                        type="file"
                        name="file"
                        accept=${this.accept}
                        aria-label=${this.t('chooseFile')}
                        @change=${this._onFileChange}
                    />
                    ${upload}
                </div>
                ${!this._pasted && this._file ? this._renderPreview() : nothing}
            </div>

            <div class="panel">
                <h3 class="heading">${this.t('pasteLabel')}</h3>
                <div class="row">
                    <ol-button class="paste-button" aria-label=${this.t('pasteAria')} @click=${this._onPaste}
                        >${this.t(this._pasted ? 'changeImage' : 'paste')}</ol-button
                    >
                    ${this._pasted ? upload : nothing}
                </div>
                ${this._pasted ? this._renderPreview() : nothing}
            </div>

            ${this._renderCandidates()}

            ${this._error ? html`<p class="status status--error" role="alert">${this._error}</p>` : nothing}
            ${this._busy ? html`<p class="status" role="status">${this.t('uploading')}</p>` : nothing}
        `;
    }
}

if (!customElements.get('ol-cover-upload')) {
    customElements.define('ol-cover-upload', OlCoverUpload);
}
