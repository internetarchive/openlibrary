import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';

import './OLButton.js';
import './OlIcon.js';
import { showToast } from './OlToastRegion.js';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';
import { translate } from './utils/labels.js';

export const DEFAULT_LABELS = {
    titleAdd: 'Add a cover',
    titleChange: 'Change the cover',
    coverHeading: 'Cover',
    currentHeading: 'Current cover',
    newHeading: 'New cover',
    emptyTitle: 'No cover yet',
    emptyHint: 'Readers see a plain placeholder on the book page, in search, and in lists.',
    noCoverTitle: 'This edition has no cover',
    noCoverIntro: 'Add one and it shows everywhere the book appears.',
    chooseHeading: 'Choose the new cover',
    replaces: 'Replaces the current cover',
    keepCurrent: 'Keep current',
    reasonHeading: 'Why are you changing this cover?',
    reasonWrong: 'It’s the wrong cover',
    reasonWrongHint: 'The image belongs to another edition or another book.',
    reasonWrongShort: 'Wrong cover',
    reasonBetter: 'Right cover, better image',
    reasonBetterHint: 'You have a sharper, cleaner, or more complete version of the same cover.',
    reasonBetterShort: 'Better image',
    reasonNotFront: 'It isn’t the front cover',
    reasonNotFrontHint: 'A title page, back cover, spine, or a “no image” placeholder.',
    reasonNotFrontShort: 'Not the front cover',
    reasonOther: 'Something else',
    reasonOtherHint: 'Tell us in a few words.',
    reasonOtherShort: 'Something else',
    reasonNoteLabel: 'What’s wrong with this cover?',
    reasonLabel: 'Reason',
    reasonChange: 'Change',
    reasonChangeLabel: 'Change the reason',
    continue: 'Continue',
    images: 'Images',
    uploadTitle: 'Upload a new image',
    addHint: 'Drop a file here, paste, or browse',
    addHintTouch: 'Take a photo or choose a file',
    fileTypes: 'JPG, GIF, PNG or WebP, up to 10 MB.',
    paste: 'Paste image',
    errorClipboard: 'No image found on your clipboard.',
    dropHere: 'Drop the image to upload it',
    current: 'Current',
    sourceArchive: 'Internet Archive',
    sourceWikidata: 'Wikidata',
    titleScanCover: 'Scan of the cover',
    titleScanTitle: 'Scan of the title page',
    titleAmazon: 'Cover from Amazon',
    titleWikidata: 'Photo on Wikimedia Commons',
    titleUploadBy: 'Uploaded by %(name)s',
    titleUpload: 'Uploaded image',
    titleYou: 'Your upload',
    detailIsbn: 'Found by ISBN %(isbn)s',
    detailJustNow: 'Just now',
    pickLabelCurrent: '%(name)s (current cover)',
    remove: 'Remove',
    removeLabel: 'Remove %(name)s',
    undo: 'Undo',
    undoLabel: 'Keep %(name)s',
    uploading: 'Uploading…',
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
    errorSave: 'Your changes couldn’t be saved. Try again.'
};

/** Why a cover is being replaced; the values match REPLACE_REASONS in plugins/upstream/covers.py. */
const REASONS = [
    { value: 'wrong', label: 'reasonWrong' },
    { value: 'better', label: 'reasonBetter' },
    { value: 'not_front', label: 'reasonNotFront' },
    { value: 'other', label: 'reasonOther' }
];

const ACCEPT = '.jpg,.jpeg,.gif,.png,.webp,image/jpeg,image/gif,image/png,image/webp';
const IMAGE_TYPES = ['image/jpeg', 'image/gif', 'image/png', 'image/webp'];
const MAX_BYTES = 10 * 1024 * 1024;
const NOTE_MAX = 200;
const CAN_READ_CLIPBOARD = typeof navigator !== 'undefined' && typeof navigator.clipboard?.read === 'function';

/**
 * Picks and manages the images for a book, work, or author: every image
 * attached to it, plus suggestions that are always listed (Internet Archive
 * scans, Amazon's cover for the ISBN, a Wikidata photo). The cover column on
 * the start side shows the current image, or the one that will replace it.
 * Replacing a book's cover asks why first. New images are added by drop,
 * paste, or file picker; uploaded images can be removed from the record.
 * Nothing is saved until Save.
 *
 * Lives inside an `<ol-dialog>`: it loads when the dialog opens, titles the
 * dialog for adding or changing, listens for pasted images while open, and
 * closes the dialog on Save or Cancel.
 *
 * @element ol-cover-manager
 *
 * @prop {String} docKey - The record whose images are managed, e.g. `/books/OL1M`.
 *     Attribute: `doc-key`.
 * @prop {String} guidelinesUrl - Link shown in the footer. Attribute: `guidelines-url`.
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS.
 *
 * @fires ol-cover-manager-save - The cover was saved. detail: { coverId: Number }
 */
export class OlCoverManager extends LitElement {
    static properties = {
        docKey: { type: String, attribute: 'doc-key' },
        guidelinesUrl: { type: String, attribute: 'guidelines-url' },
        labels: { type: Object },
        _data: { state: true },
        _loadState: { state: true },
        _step: { state: true },
        _reason: { state: true },
        _reasonNote: { state: true },
        _selected: { state: true },
        _removed: { state: true },
        _added: { state: true },
        _hidden: { state: true },
        _saving: { state: true },
        _dragging: { state: true },
        _error: { state: true }
    };

    static styles = css`
        :host {
            display: block;
            font-family: var(--font-family-body);
            color: var(--color-text);
            text-align: start;
        }

        .layout {
            display: grid;
            gap: var(--spacing-xl);
        }

        /* --width-breakpoint-tablet */
        @media (min-width: 768px) {
            .layout {
                grid-template-columns: minmax(180px, 2fr) 3fr;
                align-items: start;
            }
        }

        .overline {
            margin: 0 0 var(--spacing-sm);
            color: var(--color-text-secondary);
            font-size: var(--font-size-overline);
            font-weight: var(--font-weight-overline);
            letter-spacing: var(--letter-spacing-overline);
            text-transform: var(--text-transform-overline);
        }

        /* The cover column: the current cover, or the one Save will put in its place. */
        .cover {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-sm);
        }

        .cover-frame {
            display: grid;
            place-items: center;
            aspect-ratio: 2 / 3;
            overflow: hidden;
            border-radius: var(--border-radius-thumbnail);
        }

        /* A cover that isn't 2:3 keeps its own shape, so its caption sits right under it. */
        .cover-frame:has(img) {
            aspect-ratio: auto;
        }

        .cover-frame img {
            display: block;
            max-width: 100%;
            max-height: 420px;
            object-fit: contain;
            box-shadow: var(--box-shadow-raised);
        }

        .cover-frame.empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: var(--spacing-xs);
            padding: var(--spacing-lg);
            border: var(--border-width-thick) dashed var(--color-border);
            background: var(--color-surface-sunken);
            color: var(--color-text-secondary);
            text-align: center;
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-body);
            box-sizing: border-box;
        }

        .cover-frame.empty strong {
            color: var(--color-text);
            font-size: var(--font-size-title-small);
            font-weight: var(--font-weight-subheading);
        }

        .cover-frame.empty ol-icon {
            color: var(--color-text-secondary);
        }

        /* On a phone the cover sits beside its caption, so the steps stay in view. */
        @media (max-width: 767px) {
            .cover-body {
                display: grid;
                grid-template-columns: 96px 1fr;
                gap: var(--spacing-md);
                align-items: start;
            }

            .cover-frame.empty {
                padding: var(--spacing-xs);
            }

            .cover-frame.empty span {
                display: none;
            }
        }

        .cover-caption {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-sm);
            min-width: 0;
            margin-top: var(--spacing-sm);
        }

        @media (max-width: 767px) {
            .cover-caption {
                margin-top: 0;
            }
        }

        .aside {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--spacing-xs) var(--spacing-sm);
            padding: var(--spacing-xs) var(--spacing-sm);
            border-radius: var(--border-radius-card);
            background: var(--color-surface-sunken);
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-meta);
        }

        .aside img {
            width: 24px;
            height: 36px;
            object-fit: cover;
            border-radius: var(--border-radius-sm);
        }

        .aside .label {
            color: var(--color-text-secondary);
        }

        .aside strong {
            font-weight: var(--font-weight-semibold);
        }

        /* The heading over the list, with the reason given on the reason step at its end. */
        .pick-head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: var(--spacing-xs) var(--spacing-md);
            margin-bottom: var(--spacing-sm);
        }

        .pick-head .overline {
            flex: none;
            margin: 0;
        }

        .reason-summary {
            display: flex;
            align-items: baseline;
            gap: var(--spacing-xs);
            min-width: 0;
            margin: 0;
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-meta);
        }

        .reason-summary .label {
            flex: none;
            color: var(--color-text-secondary);
        }

        .reason-summary strong {
            overflow: hidden;
            font-weight: var(--font-weight-semibold);
            white-space: nowrap;
            text-overflow: ellipsis;
        }

        .reason-summary .text-action {
            flex: none;
        }

        /* The steps */
        .step-title {
            margin: 0 0 var(--spacing-xs);
            font-family: var(--font-family-heading);
            font-size: var(--font-size-title-medium);
            font-weight: var(--font-weight-heading);
            line-height: var(--line-height-heading);
            text-wrap: balance;
        }

        .panel > h3:focus {
            outline: none;
        }

        .step-intro {
            margin: 0 0 var(--spacing-lg);
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-body);
        }

        .reasons {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-sm);
            margin: var(--spacing-md) 0 0;
            padding: 0;
            list-style: none;
        }

        /* A reason moves straight on; "Something else" opens its note instead. */
        .reason {
            display: flex;
            align-items: center;
            gap: var(--spacing-md);
            width: 100%;
            padding: var(--spacing-md);
            border: var(--border-width-thin) solid var(--color-border-subtle);
            border-radius: var(--border-radius-card);
            background: var(--color-surface);
            color: var(--color-text-secondary);
            font: inherit;
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-body);
            text-align: start;
            cursor: pointer;
            box-sizing: border-box;
        }

        .reason:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .reason[aria-pressed='true'] {
            border-color: var(--color-primary);
            background: var(--color-control-selected-bg);
            box-shadow: 0 0 0 var(--border-width-thin) var(--color-primary);
        }

        .reason > span {
            flex: 1;
            min-width: 0;
        }

        .reason ol-icon {
            flex: none;
            color: var(--color-text-secondary);
        }

        :host(:dir(rtl)) .reason .forward {
            transform: scaleX(-1);
        }

        .reason strong {
            display: block;
            color: var(--color-text);
            font-size: var(--font-size-body-medium);
            font-weight: var(--font-weight-semibold);
        }

        .note-actions {
            display: flex;
            justify-content: flex-end;
        }

        .note {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-xs);
            margin: var(--spacing-md) 0;
            font-size: var(--font-size-label-large);
            font-weight: var(--font-weight-medium);
        }

        /* 16px so iOS doesn't zoom on focus. */
        .note input {
            min-height: var(--control-height-medium);
            padding: 0 var(--spacing-sm);
            border: var(--border-width-thin) solid var(--color-border);
            border-radius: var(--border-radius-input);
            background: var(--color-surface);
            color: var(--color-text);
            font: inherit;
            font-size: 16px;
            font-weight: var(--font-weight-regular);
            box-sizing: border-box;
        }

        .note input:focus-visible {
            border-color: var(--color-border-focused);
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 0;
        }

        /* The options: one row per image, the upload row first. */
        .list-wrap {
            position: relative;
        }

        .options {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-sm);
            margin: 0;
            padding: 0;
            list-style: none;
        }

        .row {
            position: relative;
        }

        .option {
            display: flex;
            align-items: center;
            gap: var(--spacing-md);
            width: 100%;
            min-height: 84px;
            padding: var(--spacing-sm);
            padding-inline-end: var(--spacing-md);
            border: var(--border-width-thin) solid var(--color-border-subtle);
            border-radius: var(--border-radius-card);
            background: var(--color-surface);
            color: inherit;
            font: inherit;
            text-align: start;
            cursor: pointer;
            box-sizing: border-box;
        }

        .option:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .option[aria-pressed='true'] {
            border-color: var(--color-primary);
            background: var(--color-control-selected-bg);
            box-shadow: 0 0 0 var(--border-width-thin) var(--color-primary);
        }

        .option:disabled {
            cursor: default;
        }

        /* Room for Remove / Undo, which sits over the row's end. */
        .row.removable .option {
            padding-inline-end: calc(var(--spacing-md) + 64px);
        }

        .thumb {
            position: relative;
            flex: none;
            display: grid;
            place-items: center;
            width: 56px;
            height: 84px;
            overflow: hidden;
            border-radius: var(--border-radius-sm);
        }

        .thumb img {
            display: block;
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            box-shadow: var(--box-shadow-raised);
        }

        .removed .thumb img {
            opacity: 0.3;
        }

        .upload .thumb {
            border: var(--border-width-thick) dashed var(--color-border);
            background: var(--color-surface-sunken);
            color: var(--color-text-secondary);
            box-sizing: border-box;
        }

        .upload .option {
            background: var(--color-surface-raised);
        }

        /* Drawn like the reason step's native radios; the upload row keeps the space so thumbnails line up. */
        .radio {
            flex: none;
            display: grid;
            place-items: center;
            width: 18px;
            height: 18px;
            border: var(--border-width-thin) solid var(--color-border);
            border-radius: var(--border-radius-circle);
            background: var(--color-surface);
            box-sizing: border-box;
        }

        .upload .radio {
            visibility: hidden;
        }

        .option[aria-pressed='true'] .radio {
            border-color: var(--color-primary);
            background: var(--color-primary);
        }

        .option[aria-pressed='true'] .radio::after {
            content: '';
            width: 6px;
            height: 6px;
            border-radius: var(--border-radius-circle);
            background: var(--color-on-primary);
        }

        .option:disabled .radio {
            opacity: 0.4;
        }

        .busy {
            position: absolute;
            inset: 0;
            display: grid;
            place-items: center;
            background: color-mix(in srgb, var(--color-surface) 70%, transparent);
        }

        .busy ol-icon {
            animation: spin var(--duration-spin) linear infinite;
        }

        @keyframes spin {
            to {
                transform: rotate(360deg);
            }
        }

        .text {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-3xs);
            min-width: 0;
        }

        .title {
            overflow: hidden;
            font-size: var(--font-size-body-medium);
            font-weight: var(--font-weight-semibold);
            line-height: var(--line-height-meta);
            white-space: nowrap;
            text-overflow: ellipsis;
        }

        .meta {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--spacing-xs);
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-meta);
        }

        .source,
        .tag {
            padding: var(--spacing-3xs) var(--spacing-xs);
            border-radius: var(--border-radius-badge);
            font-size: var(--font-size-label-small);
            font-weight: var(--font-weight-semibold);
            line-height: var(--line-height-single);
        }

        .source {
            background: var(--color-info-bg);
            color: var(--color-info-fg);
        }

        .tag {
            background: var(--color-surface-inverse);
            color: var(--color-text-inverse);
        }

        /* Remove / Undo and the reason's Change: quiet text links. */
        .text-action {
            padding: 0;
            border: 0;
            background: none;
            color: var(--color-link);
            font: inherit;
            text-decoration: underline;
            text-underline-offset: 2px;
            cursor: pointer;
        }

        .row .text-action {
            position: absolute;
            top: 50%;
            inset-inline-end: var(--spacing-md);
            transform: translateY(-50%);
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-small);
        }

        .row .text-action.danger {
            color: var(--color-error-fg);
        }

        .text-action:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
            border-radius: var(--border-radius-sm);
        }

        .list-note {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: var(--spacing-sm);
            margin: var(--spacing-sm) 0 0;
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-body);
        }

        /* Touch gets a Paste button and its own hint; a mouse has Cmd/Ctrl+V and drag and drop. */
        .hint-pointer {
            display: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .hint-touch,
            .paste {
                display: none;
            }

            .hint-pointer {
                display: inline;
            }

            .option:hover:not(:disabled):not([aria-pressed='true']),
            .reason:hover:not([aria-pressed='true']) {
                background: var(--color-hover-overlay);
                border-color: var(--color-border-muted);
            }

            .upload .option:hover {
                border-color: var(--color-primary);
                background: var(--color-primary-subtle);
            }

            .upload .option:hover .thumb {
                border-color: var(--color-primary);
                color: var(--color-primary);
            }

            .text-action:hover {
                text-decoration-thickness: 2px;
            }

            .row .text-action:not(.danger):hover {
                color: var(--color-text);
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
            flex: 1 1 220px;
            margin: 0;
            color: var(--color-text-secondary);
            font-size: var(--font-size-body-small);
            line-height: var(--line-height-body);
        }

        .actions {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: flex-end;
            gap: var(--spacing-sm) var(--spacing-lg);
            margin-inline-start: auto;
        }

        .actions a {
            color: var(--color-link);
            font-size: var(--font-size-body-small);
        }

        .buttons {
            display: flex;
            gap: var(--spacing-sm);
        }

        .skeleton {
            background: var(--color-surface-sunken);
            animation: pulse var(--duration-slower) var(--ease-in-out-cubic) infinite alternate;
        }

        .skeleton-row {
            height: 84px;
            border-radius: var(--border-radius-card);
        }

        @keyframes pulse {
            to {
                opacity: 0.5;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            .skeleton,
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
        this._step = 'pick';
        this._reason = null;
        this._reasonNote = '';
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
        this._onPaste = e => this._handlePaste(e);
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
            this._step = this._asksReason ? 'reason' : 'pick';
            if (this._dialog) this._dialog.label = this._t(this._data.current ? 'titleChange' : 'titleAdd');
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
        this._reason = null;
        this._reasonNote = '';
        this._error = '';
        this._saving = false;
        this._dragging = false;
        this._dragDepth = 0;
    }

    /** Replacing a book's cover asks why first; an author photo doesn't. */
    get _asksReason() {
        return Boolean(this._data?.current) && !this.docKey.startsWith('/authors/');
    }

    /** Session uploads first, after the suggestions; then what the record already has. */
    get _items() {
        const items = this._data?.items ?? [];
        const suggested = items.filter(item => item.kind !== 'upload');
        const uploads = items.filter(item => item.kind === 'upload');
        return [...suggested, ...this._added, ...uploads].filter(item => !this._hidden.has(item.id));
    }

    get _uploadedIds() {
        return this._added.filter(item => !item.pending && !this._removed.has(item.image_id)).map(item => item.image_id);
    }

    get _isDirty() {
        return Boolean(this._data) && (this._selected !== this._data.current || this._removed.size > 0 || this._uploadedIds.length > 0);
    }

    get _reasonComplete() {
        return Boolean(this._reason) && (this._reason !== 'other' || this._reasonNote.trim() !== '');
    }

    _isOpen() {
        return this._dialog ? this._dialog.open : this.isConnected;
    }

    _accepting() {
        return this._loadState === 'ready' && this._step === 'pick';
    }

    // The reason step

    async _chooseReason(value) {
        this._reason = value;
        if (value !== 'other') {
            this._continue();
            return;
        }
        await this.updateComplete;
        this.shadowRoot.querySelector('.note input')?.focus();
    }

    async _continue() {
        if (!this._reasonComplete) return;
        this._step = 'pick';
        await this.updateComplete;
        this.shadowRoot.querySelector('.panel > h3')?.focus();
    }

    async _changeReason() {
        this._step = 'reason';
        await this.updateComplete;
        (this.shadowRoot.querySelector('.reason[aria-pressed="true"]') ?? this.shadowRoot.querySelector('.reason'))?.focus();
    }

    // Adding images

    _openPicker() {
        this.shadowRoot.querySelector('input[type="file"]')?.click();
    }

    _onFileInput(e) {
        this._addFiles([...e.target.files]);
        e.target.value = '';
    }

    /** Touch devices have no paste shortcut, so the Paste button reads the clipboard directly. */
    async _pasteFromClipboard() {
        this._error = '';
        const files = [];
        try {
            for (const item of await navigator.clipboard.read()) {
                const type = item.types.find(t => IMAGE_TYPES.includes(t));
                if (type) files.push(new File([await item.getType(type)], 'pasted', { type }));
            }
        } catch {
            // Permission denied or nothing readable: same message as an empty clipboard.
        }
        if (files.length) this._addFiles(files);
        else this._error = this._t('errorClipboard');
    }

    _handlePaste(e) {
        if (!this._isOpen() || !this._accepting()) return;
        const files = [...(e.clipboardData?.files ?? [])].filter(file => file.type.startsWith('image/'));
        if (!files.length) return;
        e.preventDefault();
        this._addFiles(files);
    }

    _hasFiles(e) {
        return [...(e.dataTransfer?.types ?? [])].includes('Files');
    }

    _onDragEnter(e) {
        if (!this._hasFiles(e) || !this._accepting()) return;
        e.preventDefault();
        this._dragDepth += 1;
        this._dragging = true;
    }

    _onDragOver(e) {
        if (!this._hasFiles(e) || !this._accepting()) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    }

    _onDragLeave(e) {
        if (!this._hasFiles(e)) return;
        this._dragDepth = Math.max(0, this._dragDepth - 1);
        if (this._dragDepth === 0) this._dragging = false;
    }

    _onDrop(e) {
        if (!this._hasFiles(e) || !this._accepting()) return;
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
        const placeholder = { id: `pending:${this._pendingCount}`, kind: 'upload', pending: true, thumb: objectUrl, objectUrl };
        this._added = [placeholder, ...this._added];

        const body = new FormData();
        // Send a neutral name: the firewall rejects some real ones (apostrophes, #13286), and the server only checks the extension.
        body.append('file', file, `image.${file.type === 'image/jpeg' ? 'jpg' : file.type.split('/')[1]}`);
        try {
            const response = await fetch(`${this._endpoint}/upload.json`, { method: 'POST', body, credentials: 'same-origin' });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.detail || response.statusText);
            // Keep showing the local preview: the coverstore may still be making its thumbnails.
            const item = { ...result, thumb: objectUrl, preview: objectUrl, objectUrl, session: true };
            this._added = this._added.map(added => (added.id === placeholder.id ? item : added));
            this._selected = item.id;
        } catch {
            URL.revokeObjectURL(objectUrl);
            this._added = this._added.filter(added => added.id !== placeholder.id);
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
        // A scan page that doesn't exist (many items have no title page) 404s; drop its row.
        if (item.kind === 'upload' || item.id === this._selected) return;
        this._hidden = new Set(this._hidden).add(item.id);
    }

    /** Amazon answers a 1x1 GIF when it has no cover for the ISBN. */
    _onThumbLoad(e, item) {
        if (e.target.naturalWidth < 10) this._hide(item);
    }

    _onListKeydown(e) {
        const options = [...this.shadowRoot.querySelectorAll('.option')];
        const current = options.indexOf(this.shadowRoot.activeElement);
        if (current === -1) return;
        const next = getNextKeyboardFocusIndex(e.key, {
            count: options.length,
            current,
            orientation: 'vertical',
            wrap: false,
            isDisabled: i => options[i].disabled
        });
        if (next === -1) return;
        e.preventDefault();
        options[next].focus();
    }

    // Saving

    async _save() {
        if (!this._isDirty || this._saving) return;
        this._saving = true;
        this._error = '';
        // An image the record has is picked by id; a suggestion not copied in yet, by name.
        const selected = this._items.find(item => item.id === this._selected);
        const selection = selected.image_id ? { image_id: selected.image_id } : { suggestion: selected.suggestion };
        const reason = this._reason ? { reason: this._reason, ...(this._reason === 'other' ? { reason_note: this._reasonNote.trim() } : {}) } : {};
        try {
            const response = await fetch(`${this._endpoint}.json`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ ...selection, added: this._uploadedIds, removed: [...this._removed], ...reason })
            });
            if (!response.ok) throw new Error(response.statusText);
            const { cover_id: coverId } = await response.json();
            this.dispatchEvent(
                new CustomEvent('ol-cover-manager-save', {
                    detail: { coverId },
                    bubbles: true,
                    composed: true
                })
            );
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

    /** A row's title line and its meta line: a source tag for suggestions, a date for uploads. */
    _describe(item) {
        switch (item.kind) {
            case 'archive_cover':
                return { title: this._t('titleScanCover'), source: this._t('sourceArchive') };
            case 'archive_title':
                return { title: this._t('titleScanTitle'), source: this._t('sourceArchive') };
            case 'amazon':
                return { title: this._t('titleAmazon'), detail: item.isbn ? this._t('detailIsbn', { isbn: item.isbn }) : '' };
            case 'wikidata':
                return { title: this._t('titleWikidata'), source: this._t('sourceWikidata') };
            default: {
                if (item.session || item.pending) return { title: this._t('titleYou'), detail: this._t('detailJustNow') };
                const uploader = item.added_by?.name;
                const date = item.created
                    ? new Intl.DateTimeFormat(document.documentElement.lang || 'en', { month: 'long', year: 'numeric' }).format(new Date(item.created))
                    : '';
                return { title: uploader ? this._t('titleUploadBy', { name: uploader }) : this._t('titleUpload'), detail: date };
            }
        }
    }

    _name({ title, source, detail }) {
        return [title, source, detail].filter(Boolean).join(', ');
    }

    _renderMeta({ source, detail }, tag) {
        if (!source && !detail && !tag) return nothing;
        return html`<span class="meta"
            >${tag ? html`<span class="tag">${tag}</span>` : nothing}${source ? html`<span class="source">${source}</span>` : nothing}${
                detail ? html`<span>${detail}</span>` : nothing
            }</span
        >`;
    }

    _renderCover() {
        const items = this._items;
        const selected = items.find(item => item.id === this._selected);
        const current = items.find(item => item.id === this._data.current);
        const heading = !selected ? 'coverHeading' : selected === current ? 'currentHeading' : 'newHeading';
        const description = selected && this._describe(selected);

        return html`<section class="cover" aria-labelledby="cover-heading">
            <h3 class="overline" id="cover-heading">${this._t(heading)}</h3>
            <div class="cover-body">
                ${
                    selected
                        ? html`<div class="cover-frame"><img src=${selected.preview ?? selected.thumb} alt="" /></div>`
                        : html`<div class="cover-frame empty">
                              <ol-icon name="image" size="lg"></ol-icon>
                              <strong>${this._t('emptyTitle')}</strong>
                              <span>${this._t('emptyHint')}</span>
                          </div>`
                }
                <div class="cover-caption">
                    ${description ? html`<div class="text"><span class="title">${description.title}</span>${this._renderMeta(description)}</div>` : nothing}
                    ${
                        current && selected !== current
                            ? html`<div class="aside">
                                  <img src=${current.thumb} alt="" />
                                  <span class="label">${this._t('replaces')}</span>
                                  <button type="button" class="text-action" @click=${() => this._select(current)}>${this._t('keepCurrent')}</button>
                              </div>`
                            : nothing
                    }
                </div>
            </div>
        </section>`;
    }

    _renderReasonSummary() {
        if (!this._reason) return nothing;
        const reason = this._reason === 'other' ? this._reasonNote.trim() : this._t(`${REASONS.find(r => r.value === this._reason).label}Short`);
        return html`<p class="reason-summary">
            <span class="label">${this._t('reasonLabel')}</span>
            <strong title=${reason}>${reason}</strong>
            <button type="button" class="text-action" aria-label=${this._t('reasonChangeLabel')} @click=${this._changeReason}>
                ${this._t('reasonChange')}
            </button>
        </p>`;
    }

    _renderReasonStep() {
        return html`<div class="panel">
            <h3 class="step-title" id="reason-heading" tabindex="-1">${this._t('reasonHeading')}</h3>
            <ul class="reasons" aria-labelledby="reason-heading">
                ${REASONS.map(
                    ({ value, label }) =>
                        html`<li>
                            <button
                                class="reason"
                                type="button"
                                data-value=${value}
                                aria-pressed=${this._reason === value ? 'true' : 'false'}
                                @click=${() => this._chooseReason(value)}
                            >
                                <span><strong>${this._t(label)}</strong>${this._t(`${label}Hint`)}</span>
                                ${value === 'other' ? html`<ol-icon name="chevron-down"></ol-icon>` : html`<ol-icon class="forward" name="chevron-right"></ol-icon>`}
                            </button>
                        </li>`
                )}
            </ul>
            ${
                this._reason === 'other'
                    ? html`<label class="note">
                              ${this._t('reasonNoteLabel')}
                              <input
                                  type="text"
                                  maxlength=${NOTE_MAX}
                                  .value=${this._reasonNote}
                                  @input=${e => (this._reasonNote = e.target.value)}
                                  @keydown=${e => e.key === 'Enter' && this._continue()}
                              />
                          </label>
                          <div class="note-actions">
                              <ol-button class="note-continue" variant="primary" ?disabled=${!this._reasonComplete} @click=${this._continue}
                                  >${this._t('continue')}</ol-button
                              >
                          </div>`
                    : nothing
            }
        </div>`;
    }

    _renderRow(item) {
        const description = this._describe(item);
        const name = this._name(description);
        const selected = item.id === this._selected;
        const isCurrent = item.id === this._data.current;
        const removed = this._removed.has(item.image_id);
        // Suggestions stay listed; an upload, even the current cover, can go once another image is picked.
        const canRemove = item.kind === 'upload' && !item.pending && !selected;
        const label = isCurrent ? this._t('pickLabelCurrent', { name }) : name;

        return html`<li class="row ${removed ? 'removed' : ''} ${canRemove || removed ? 'removable' : ''}">
            <button
                class="option"
                type="button"
                aria-pressed=${selected ? 'true' : 'false'}
                aria-label=${label}
                ?disabled=${removed || item.pending}
                @click=${() => this._select(item)}
            >
                <span class="radio" aria-hidden="true"></span>
                <span class="thumb">
                    <img src=${item.thumb} alt="" loading="lazy" @load=${e => this._onThumbLoad(e, item)} @error=${() => this._hide(item)} />
                    ${item.pending ? html`<span class="busy"><ol-icon name="loader"></ol-icon></span>` : nothing}
                </span>
                <span class="text" aria-hidden="true">
                    <span class="title" title=${description.title}>${description.title}</span>
                    ${this._renderMeta(description, isCurrent ? this._t('current') : '')}
                </span>
            </button>
            ${
                canRemove && !removed
                    ? html`<button type="button" class="text-action danger" aria-label=${this._t('removeLabel', { name })} @click=${() => this._remove(item)}>
                          ${this._t('remove')}
                      </button>`
                    : nothing
            }
            ${removed ? html`<button type="button" class="text-action" aria-label=${this._t('undoLabel', { name })} @click=${() => this._undoRemove(item)}>${this._t('undo')}</button>` : nothing}
        </li>`;
    }

    _renderPickStep() {
        const hasCover = Boolean(this._data.current);
        return html`<div class="panel">
            ${
                hasCover
                    ? html`<div class="pick-head">
                          <h3 class="overline" tabindex="-1">${this._t('chooseHeading')}</h3>
                          ${this._renderReasonSummary()}
                      </div>`
                    : html`<h3 class="step-title" tabindex="-1">${this._t('noCoverTitle')}</h3>
                          <p class="step-intro">${this._t('noCoverIntro')}</p>`
            }
            <div class="list-wrap" @dragenter=${this._onDragEnter} @dragover=${this._onDragOver} @dragleave=${this._onDragLeave} @drop=${this._onDrop}>
                <ul class="options" aria-label=${this._t('images')} @keydown=${this._onListKeydown}>
                    <li class="row upload">
                        <button class="option" type="button" @click=${this._openPicker}>
                            <span class="radio" aria-hidden="true"></span>
                            <span class="thumb"><ol-icon name="upload"></ol-icon></span>
                            <span class="text">
                                <span class="title">${this._t('uploadTitle')}</span>
                                <span class="meta"
                                    ><span class="hint-touch">${this._t('addHintTouch')}</span><span class="hint-pointer">${this._t('addHint')}</span></span
                                >
                            </span>
                        </button>
                        <input class="visually-hidden" type="file" accept=${ACCEPT} multiple tabindex="-1" aria-hidden="true" @change=${this._onFileInput} />
                    </li>
                    ${repeat(
                        this._items,
                        item => item.id,
                        item => this._renderRow(item)
                    )}
                </ul>
                ${this._dragging ? html`<div class="drop-target">${this._t('dropHere')}</div>` : nothing}
            </div>
            <p class="list-note">
                <span>${this._t('fileTypes')}</span>
                ${
                    CAN_READ_CLIPBOARD
                        ? html`<ol-button class="paste" variant="secondary" size="small" @click=${this._pasteFromClipboard}>${this._t('paste')}</ol-button>`
                        : nothing
                }
            </p>
        </div>`;
    }

    _renderStatus() {
        if (this._step === 'reason') return nothing;
        if (this._added.some(item => item.pending)) return this._t('uploading');
        if (!this._isDirty) return nothing;
        const parts = [];
        const newUploads = this._uploadedIds.filter(id => `img:${id}` !== this._selected).length;
        if (newUploads) parts.push(this._t('statusAdd', { count: newUploads }));
        if (this._removed.size) parts.push(this._t('statusRemove', { count: this._removed.size }));
        return parts.join(' ');
    }

    _renderFooter() {
        const pending = this._added.some(item => item.pending);
        const primary =
            this._step === 'reason'
                ? nothing
                : html`<ol-button variant="primary" ?disabled=${!this._isDirty || pending} ?loading=${this._saving} @click=${this._save}
                      >${this._t('save')}</ol-button
                  >`;
        return html`<div class="footer">
            <p class="status" aria-live="polite">${this._renderStatus()}</p>
            <div class="actions">
                <a href=${this.guidelinesUrl} target="_blank" rel="noopener">${this._t('guidelines')}</a>
                <div class="buttons">
                    <ol-button variant="secondary" @click=${this._cancel}>${this._t('cancel')}</ol-button>
                    ${primary}
                </div>
            </div>
        </div>`;
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
            return html`<div class="layout" aria-busy="true" aria-label=${this._t('loading')}>
                <div class="cover"><div class="cover-frame skeleton"></div></div>
                <div class="options">${[0, 1, 2].map(() => html`<div class="skeleton skeleton-row"></div>`)}</div>
            </div>`;
        }

        return html`
            <div class="layout">${this._renderCover()} ${this._step === 'reason' ? this._renderReasonStep() : this._renderPickStep()}</div>
            ${this._error ? html`<p class="error" role="alert"><ol-icon name="circle-alert" size="sm"></ol-icon>${this._error}</p>` : nothing}
            ${this._renderFooter()}
        `;
    }
}

customElements.define('ol-cover-manager', OlCoverManager);
