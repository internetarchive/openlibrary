import { LitElement, html, css, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
// Registers <ol-button> for the actions, <ol-icon> for the glyphs, and
// <ol-tooltip> for the delete affordance.
import './OLButton.js';
import './OlIcon.js';
import './OlTooltip.js';
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
    coversHeading: 'Covers',
    photosHeading: 'Photos',
    reorderHint: 'Drag to reorder, or click an image to make it primary.',
    coverPrimary: 'Primary',
    imagePosition: 'Image %(position)s of %(total)s',
    chooseFile: 'Choose an image',
    browse: 'Browse',
    dropHint: 'Drag and drop or paste an image here',
    useImageFrom: 'Or, use an image from %(source)s',
    uploadImage: 'Upload Image',
    paste: 'Paste Image',
    changeImage: 'Change Image',
    pasteAria: 'Paste image from clipboard',
    previewAlt: 'Selected image preview',
    removeImage: 'Remove image',
    upload: 'Upload',
    uploading: 'Uploading…',
    saving: 'Saving…',
    imageAdded: 'Image added.',
    imageRemoved: 'Image removed.',
    undo: 'Undo',
    movedImage: 'Moved image to position %(position)s of %(total)s.',
    noFile: 'Please choose an image first.',
    invalidType: 'That file type isn\'t supported. Please use one of these image types: %(types)s.',
    uploadFailed: 'Could not upload the image. Please try again.',
    saveFailed: 'Could not save your changes. Please try again.',
    noClipboardImage: 'No image found in clipboard',
};

/** Extension → MIME types, for files (e.g. pasted) with no usable filename. */
const EXTENSION_MIME = {
    '.jpg': ['image/jpeg', 'image/jpg'],
    '.jpeg': ['image/jpeg', 'image/jpg'],
    '.gif': ['image/gif'],
    '.png': ['image/png'],
    '.webp': ['image/webp'],
};

/**
 * One interface for a document's images: the current cover/photo set with the
 * first as primary, drag (or arrow-key) reordering and delete, plus adding a
 * new one by upload, drop, paste or an external candidate.
 *
 * Replaces both `covers/add.html` and `covers/manage.html` iframes. Adding uses
 * the existing `…/add-cover` POST (which prepends and saves); reordering and
 * deleting POST the ordered id list to `…/manage-covers`. Both responses are
 * HTML — this component only needs the new id / an ok status.
 *
 * @element ol-cover-editor
 *
 * @prop {String} action - add POST target, e.g. `/books/OL1M/add-cover`
 * @prop {String} manageUrl - reorder/delete POST target; attribute `manage-url`
 * @prop {String} docType - `/type/work`, `/type/edition`, or `/type/author`
 * @prop {String} coverSelector - CSS selector for the page's cover `<img>`
 * @prop {String} coverstoreUrl - Public coverstore base URL
 * @prop {String} accept - Accepted file types
 * @prop {Array} images - Current images, `[{ id, url }]`, first is primary
 * @prop {Array} candidates - Importable remote images, `[{ url, source }]`
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-cover-editor-add - An image was added. detail: { id }
 * @fires ol-cover-editor-order - The order changed. detail: { ids }
 */
export class OlCoverEditor extends LitElement {
    static properties = {
        action: { type: String },
        manageUrl: { type: String, attribute: 'manage-url' },
        docType: { type: String, attribute: 'doc-type' },
        coverSelector: { type: String, attribute: 'cover-selector' },
        coverstoreUrl: { type: String, attribute: 'coverstore-url' },
        accept: { type: String },
        images: { type: Array },
        candidates: { type: Array },
        labels: { type: Object },
        _images: { state: true },
        _file: { state: true },
        _previewUrl: { state: true },
        _busy: { state: true },
        _saving: { state: true },
        _error: { state: true },
        _pasted: { state: true },
        _dragging: { state: true },
        _dragIndex: { state: true },
        _status: { state: true },
        _announce: { state: true },
        _removedImage: { state: true },
        _focusIndex: { state: true },
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

        .panel {
            padding: var(--spacing-md);
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

        .hint {
            margin: var(--spacing-2xs) 0 0;
            color: var(--color-text-muted);
            font-size: var(--font-size-label-medium);
        }

        /* ── Current images (a horizontal strip) ──────────────────────── */

        .images {
            display: flex;
            gap: var(--spacing-sm);
            margin: var(--spacing-sm) 0 0;
            padding: 0 0 var(--spacing-3xs);
            list-style: none;
            overflow-x: auto;
        }

        .image {
            position: relative;
            flex: none;
            width: 72px;
            aspect-ratio: 2 / 3;
            border-radius: var(--border-radius-thumbnail);
            overflow: hidden;
            background: var(--color-surface-sunken);
            cursor: grab;
            outline: none;
        }

        .image:focus-visible {
            box-shadow: var(--box-shadow-focus);
        }

        .image--primary {
            box-shadow: 0 0 0 var(--border-width-thick) var(--color-primary);
        }

        .image--dragging {
            opacity: 0.4;
        }

        .image__img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
            pointer-events: none;
        }

        .image__badge {
            position: absolute;
            left: var(--spacing-2xs);
            bottom: var(--spacing-2xs);
            padding: 1px var(--spacing-2xs);
            border-radius: var(--border-radius-sm);
            background: var(--color-primary);
            color: var(--color-text-inverse);
            font-size: var(--font-size-label-small);
            font-weight: var(--font-weight-semibold);
        }

        /* The delete control, revealed on hover/focus — always on touch, where
           there is no hover. */
        .image__actions {
            position: absolute;
            top: var(--spacing-2xs);
            right: var(--spacing-2xs);
            opacity: 0;
            transition: opacity var(--duration-fast) var(--ease-state);
        }

        .image:hover .image__actions,
        .image:focus-visible .image__actions,
        .image:focus-within .image__actions {
            opacity: 1;
        }

        @media (hover: none) {
            .image__actions {
                opacity: 1;
            }
        }

        /* ── Add panel (whole panel is a drop target) ─────────────────── */

        .dropzone {
            border: var(--border-width-thick) dashed var(--color-border-muted);
            transition:
                border-color var(--duration-fast) var(--ease-state),
                background-color var(--duration-fast) var(--ease-state);
        }

        .dropzone--active {
            border-color: var(--color-primary);
            background: var(--color-control-selected-bg);
        }

        .drop-content {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 96px;
            margin-bottom: var(--spacing-sm);
        }

        .dropzone__hint {
            margin: 0;
            color: var(--color-text-muted);
        }

        .row {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--spacing-sm);
        }

        .file {
            display: none;
        }

        /* Desktop has Ctrl/⌘V and drag-and-drop, so the Paste button is only a
           touch affordance (there's no keyboard shortcut there). */
        .paste-button {
            display: none;
        }

        @media (hover: none) {
            .paste-button {
                display: inline-block;
            }
        }

        .preview-wrap {
            position: relative;
            display: inline-block;
        }

        .preview {
            display: block;
            max-width: 200px;
            max-height: 200px;
            border: var(--border-width) solid var(--color-control-border);
            border-radius: var(--border-radius-thumbnail);
        }

        .preview-clear {
            position: absolute;
            top: var(--spacing-2xs);
            right: var(--spacing-2xs);
        }

        /* ── External candidates ──────────────────────────────────────── */

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

        /* ── Status ───────────────────────────────────────────────────── */

        .status {
            margin: var(--spacing-sm) 0 0;
            line-height: var(--line-height-body);
        }

        .status--error {
            color: var(--color-error-fg);
        }

        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }
    `;

    constructor() {
        super();
        this.action = '';
        this.manageUrl = '';
        this.docType = '';
        this.coverSelector = '.bookCover img';
        this.coverstoreUrl = '';
        this.accept = '.jpg,.jpeg,.gif,.png,.webp';
        this.images = [];
        this.candidates = [];
        this.labels = {};
        this._images = [];
        this._file = null;
        this._previewUrl = '';
        this._busy = false;
        this._saving = false;
        this._error = '';
        this._pasted = false;
        this._dragging = false;
        this._dragIndex = null;
        this._status = '';
        this._announce = '';
        this._removedImage = null;
        this._focusIndex = null;
        this._imagesEdited = false;
        /** Snapshots of `_images` for undo (⌘Z). */
        this._history = [];
        this._onPasteEvent = this._onPasteEvent.bind(this);
        this._onDialogClose = this._onDialogClose.bind(this);
        this._onKeydown = this._onKeydown.bind(this);
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

    /** Extensions from the `accept` list, e.g. ['.jpg', '.png']. */
    get _acceptedExtensions() {
        return (this.accept || '')
            .split(',')
            .map((s) => s.trim().toLowerCase())
            .filter((s) => s.startsWith('.'));
    }

    connectedCallback() {
        super.connectedCallback();
        // Cmd/Ctrl+V anywhere while the dialog is open hands us the image
        // directly, with no clipboard permission prompt (unlike the button).
        document.addEventListener('paste', this._onPasteEvent);
        document.addEventListener('keydown', this._onKeydown);
        this.closest('ol-dialog')?.addEventListener('ol-after-close', this._onDialogClose);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('paste', this._onPasteEvent);
        document.removeEventListener('keydown', this._onKeydown);
        this.closest('ol-dialog')?.removeEventListener('ol-after-close', this._onDialogClose);
        this._revokePreview();
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        // Seed the working list from the `images` prop until the user edits it.
        if (!this._imagesEdited && changed.has('images')) {
            this._images = (this.images ?? []).map((image) => ({ ...image }));
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('_images') && this._focusIndex !== null) {
            const index = this._focusIndex;
            this._focusIndex = null;
            requestAnimationFrame(() => this.renderRoot.querySelectorAll('.image')[index]?.focus());
        }
    }

    /** Clear the pending pick/paste; keeps the current image list. */
    reset() {
        this._revokePreview();
        this._file = null;
        this._previewUrl = '';
        this._error = '';
        this._status = '';
        this._removedImage = null;
        this._pasted = false;
        const input = this._fileInput;
        if (input) input.value = '';
    }

    _onDialogClose() {
        this.reset();
    }

    /** ⌘Z / Ctrl+Z undoes the last change to the image list. */
    _onKeydown(event) {
        if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'z') return;
        const dialog = this.closest('ol-dialog');
        if (dialog && !dialog.open) return;
        const target = event.target;
        if (target instanceof HTMLElement && (target.matches('input, textarea') || target.isContentEditable)) return;
        if (!this._history.length) return;
        event.preventDefault();
        this._undo();
    }

    _revokePreview() {
        if (this._previewUrl) URL.revokeObjectURL(this._previewUrl);
    }

    /** Discard the chosen/pasted image. */
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
        if (file) this._setFile(file);
    }

    /** Open the hidden native file picker from the Browse button. */
    _openPicker() {
        this._fileInput?.click();
    }

    /** Whether a picked / dropped / pasted file is an accepted image type. */
    _isAccepted(file) {
        const extensions = this._acceptedExtensions;
        if (!extensions.length) return true;
        const name = (file?.name || '').toLowerCase();
        if (extensions.some((ext) => name.endsWith(ext))) return true;
        const mimes = extensions.flatMap((ext) => EXTENSION_MIME[ext] ?? []);
        return mimes.includes((file?.type || '').toLowerCase());
    }

    /** "JPG, JPEG, GIF, PNG, WEBP" — the accepted types, for the error copy. */
    _acceptedTypesLabel() {
        return [...new Set(this._acceptedExtensions.map((ext) => ext.slice(1).toUpperCase()))].join(', ');
    }

    _invalidTypeMessage() {
        return this.t('invalidType', { types: this._acceptedTypesLabel() });
    }

    /** Record a chosen or dropped image and preview it. */
    _setFile(file) {
        if (!this._isAccepted(file)) {
            this._error = this._invalidTypeMessage();
            return;
        }
        this._error = '';
        this._pasted = false;
        this._file = file;
        this._showPreview(file);
    }

    /** Record an image as the pending "pasted" upload and preview it. */
    _setPastedFile(file) {
        if (!this._isAccepted(file)) {
            this._error = this._invalidTypeMessage();
            return;
        }
        this._error = '';
        this._pasted = true;
        this._file = file;
        this._showPreview(file);
    }

    _isFileDrag(event) {
        return [...(event.dataTransfer?.types ?? [])].includes('Files');
    }

    _onDragOver(event) {
        if (!this._isFileDrag(event)) return;
        event.preventDefault();
        this._dragging = true;
    }

    _onDragLeave(event) {
        if (!this._dragging) return;
        // Ignore the dragleave fired when the pointer moves onto a child.
        if (event.currentTarget?.contains(event.relatedTarget)) return;
        this._dragging = false;
    }

    _onDrop(event) {
        if (!this._isFileDrag(event)) return;
        event.preventDefault();
        this._dragging = false;
        const files = [...(event.dataTransfer?.files ?? [])];
        if (!files.length) return;
        const file = files.find((f) => this._isAccepted(f));
        if (file) this._setFile(file);
        else this._error = this._invalidTypeMessage();
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
                const imageType = item.types.find((type) => type.startsWith('image/'));
                if (!imageType) continue;
                const blob = await item.getType(imageType);
                const extension = (imageType.split('/')[1] || 'png').replace('jpeg', 'jpg');
                this._setPastedFile(new File([blob], `pasted-image.${extension}`, { type: imageType }));
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
            this._clearImage();
            this._imagesEdited = true;
            this._removedImage = null;
            this._pushHistory();
            this._images = [{ id, url: this._coverUrl(id) }, ...this._images];
            this._status = this.t('imageAdded');
            this._applyCover(id);
            this.dispatchEvent(
                new CustomEvent('ol-cover-editor-add', { bubbles: true, composed: true, detail: { id } }),
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
     * Update the cover the user sees. Mirrors the old `initCoversSaved`
     * handler, which reached into the parent document from the iframe; now it
     * is the same document, so a plain querySelector + display toggle does it.
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

    /** No images left: show the generated blank cover again. */
    _clearPageCover() {
        const img = document.querySelector(this.coverSelector);
        if (!img) return;
        if (this._isPhoto) {
            img.setAttribute('src', '/static/images/icons/avatar_author-lg.png');
            return;
        }
        img.removeAttribute('src');
        img.removeAttribute('srcset');
        const cover = img.closest('div');
        if (cover) {
            cover.style.display = 'none';
            const blank = cover.nextElementSibling;
            if (blank) blank.style.display = 'block';
        }
    }

    // ── Reorder / delete ───────────────────────────────────────────────

    _onCardDragStart(event, index) {
        this._dragIndex = index;
        event.dataTransfer.effectAllowed = 'move';
        // Some browsers refuse to start a drag without payload.
        event.dataTransfer.setData('text/plain', String(index));
    }

    _onCardDragOver(event) {
        if (this._dragIndex === null) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }

    _onCardDrop(event, index) {
        event.preventDefault();
        const from = this._dragIndex;
        this._dragIndex = null;
        if (from === null || from === index) return;
        this._moveImage(from, index);
    }

    _onCardDragEnd() {
        this._dragIndex = null;
    }

    _onCardKeydown(event, index) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            this._makePrimary(index);
            return;
        }
        const map = {
            ArrowLeft: index - 1,
            ArrowUp: index - 1,
            ArrowRight: index + 1,
            ArrowDown: index + 1,
            Home: 0,
            End: this._images.length - 1,
        };
        if (!(event.key in map)) return;
        event.preventDefault();
        const target = map[event.key];
        if (target === index || target < 0 || target >= this._images.length) return;
        this._focusIndex = target;
        this._moveImage(index, target);
    }

    /** Snapshot the current list so ⌘Z can restore it. */
    _pushHistory() {
        this._history.push(this._images.map((image) => ({ ...image })));
        if (this._history.length > 30) this._history.shift();
    }

    _moveImage(from, to) {
        if (from === to || from < 0 || to < 0 || from >= this._images.length || to >= this._images.length) return;
        this._pushHistory();
        const images = [...this._images];
        const [moved] = images.splice(from, 1);
        images.splice(to, 0, moved);
        this._imagesEdited = true;
        this._removedImage = null;
        this._status = '';
        this._images = images;
        // Announced to screen readers; the change is otherwise silent.
        this._announce = this.t('movedImage', { position: to + 1, total: images.length });
        this._syncPageCover();
        this._saveOrder();
    }

    _makePrimary(index) {
        this._focusIndex = 0;
        this._moveImage(index, 0);
    }

    /** Clicking an image promotes it to primary (front of the list). */
    _onCardClick(index) {
        if (index === 0) return;
        this._moveImage(index, 0);
    }

    _onDeleteClick(event, index) {
        event.stopPropagation();
        this._deleteImage(index);
    }

    _deleteImage(index) {
        const image = this._images[index];
        if (!image) return;
        this._pushHistory();
        this._removedImage = { image, index };
        this._imagesEdited = true;
        this._images = this._images.filter((_, i) => i !== index);
        this._syncPageCover();
        this._saveOrder();
    }

    /** Undo the last change (⌘Z, or the inline Undo after a delete). */
    _undo() {
        if (!this._history.length) return;
        this._imagesEdited = true;
        this._removedImage = null;
        this._status = '';
        this._announce = this.t('undo');
        this._images = this._history.pop();
        this._syncPageCover();
        this._saveOrder();
    }

    _syncPageCover() {
        const first = this._images[0];
        if (first) this._applyCover(first.id);
        else this._clearPageCover();
    }

    /**
     * Persist the ordered id list. The manage endpoint reads repeated `image`
     * fields, ended by `-`; the `-1` marker keeps the list non-empty so an
     * emptied set doesn't fall back to coverstore-discovered covers.
     */
    async _saveOrder() {
        if (!this.manageUrl) return;
        const data = new FormData();
        for (const image of this._images) data.append('image', image.id);
        data.append('image', '-1');
        data.append('image', '-');
        this._saving = true;
        this._error = '';
        try {
            const response = await fetch(this.manageUrl, { method: 'POST', body: data, credentials: 'same-origin' });
            if (!response.ok) throw new Error('save failed');
            this.dispatchEvent(
                new CustomEvent('ol-cover-editor-order', {
                    bubbles: true,
                    composed: true,
                    detail: { ids: this._images.map((image) => image.id) },
                }),
            );
        } catch {
            this._error = this.t('saveFailed');
        } finally {
            this._saving = false;
        }
    }

    // ── Render ─────────────────────────────────────────────────────────

    render() {
        return html`
            <p class="intro">
                ${this.t(this._isPhoto ? 'introPhoto' : 'introCover')}
                ${' '}
                ${this.t('learnMore')}
                <a href="/help/faq/editing#picture" target="_blank" rel="noopener noreferrer"
                    >${this.t(this._isPhoto ? 'guidelinesPhoto' : 'guidelinesCover')}</a
                >.
            </p>

            ${this._renderAdd()} ${this._renderCandidates()} ${this._renderImages()} ${this._renderStatus()}

            <p class="sr-only" role="status" aria-live="polite">${this._announce}</p>
        `;
    }

    _renderImages() {
        if (!this._images.length) return nothing;
        return html`
            <div class="panel">
                <h3 class="heading">${this.t(this._isPhoto ? 'photosHeading' : 'coversHeading')}</h3>
                <p class="hint">${this.t('reorderHint')}</p>
                <ul class="images" @dragend=${this._onCardDragEnd}>
                    ${this._images.map(
        (image, index) => html`
                            <li
                                class="image ${classMap({
        'image--primary': index === 0,
        'image--dragging': this._dragIndex === index,
    })}"
                                draggable="true"
                                tabindex="0"
                                aria-label=${this.t('imagePosition', { position: index + 1, total: this._images.length })}
                                @click=${() => this._onCardClick(index)}
                                @keydown=${(e) => this._onCardKeydown(e, index)}
                                @dragstart=${(e) => this._onCardDragStart(e, index)}
                                @dragover=${(e) => this._onCardDragOver(e)}
                                @drop=${(e) => this._onCardDrop(e, index)}
                            >
                                <img class="image__img" src=${image.url} alt="" draggable="false" />
                                ${index === 0
        ? html`<span class="image__badge">${this.t('coverPrimary')}</span>`
        : nothing}
                                <div class="image__actions">
                                    <ol-tooltip content=${this.t('removeImage')} placement="top">
                                        <ol-button
                                            class="image__delete"
                                            shape="icon"
                                            size="small"
                                            variant="secondary"
                                            aria-label=${this.t('removeImage')}
                                            @click=${(e) => this._onDeleteClick(e, index)}
                                        >
                                            <ol-icon name="x"></ol-icon>
                                        </ol-button>
                                    </ol-tooltip>
                                </div>
                            </li>
                        `,
    )}
                </ul>
            </div>
        `;
    }

    _renderAdd() {
        const upload = html`<ol-button
            class="upload-button"
            variant="primary"
            ?loading=${this._busy}
            ?disabled=${this._busy}
            @click=${this._onSubmit}
            >${this.t('upload')}</ol-button
        >`;
        return html`
            <div
                class="panel dropzone ${classMap({ 'dropzone--active': this._dragging })}"
                @dragover=${this._onDragOver}
                @dragleave=${this._onDragLeave}
                @drop=${this._onDrop}
            >
                <input
                    class="file"
                    type="file"
                    name="file"
                    accept=${this.accept}
                    aria-label=${this.t('chooseFile')}
                    @change=${this._onFileChange}
                />
                <div class="drop-content">
                    ${this._previewUrl ? this._renderPreview() : html`<p class="dropzone__hint">${this.t('dropHint')}</p>`}
                </div>
                <div class="row">
                    <ol-button class="browse-button" @click=${this._openPicker}>${this.t('browse')}</ol-button>
                    <ol-button class="paste-button" aria-label=${this.t('pasteAria')} @click=${this._onPaste}
                        >${this.t(this._pasted ? 'changeImage' : 'paste')}</ol-button
                    >
                    ${upload}
                </div>
            </div>
        `;
    }

    _renderStatus() {
        if (this._error) return html`<p class="status status--error" role="alert">${this._error}</p>`;
        if (this._busy) return html`<p class="status" role="status">${this.t('uploading')}</p>`;
        if (this._saving) return html`<p class="status" role="status">${this.t('saving')}</p>`;
        if (this._removedImage) {
            return html`<p class="status" role="status">
                ${this.t('imageRemoved')}
                <ol-button class="status__undo" size="small" variant="ghost" @click=${this._undo}
                    >${this.t('undo')}</ol-button
                >
            </p>`;
        }
        if (this._status) return html`<p class="status" role="status">${this._status}</p>`;
        return nothing;
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
}

if (!customElements.get('ol-cover-editor')) {
    customElements.define('ol-cover-editor', OlCoverEditor);
}
