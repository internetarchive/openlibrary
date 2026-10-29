import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';

import './OLButton.js';
import './OlIcon.js';
import { focusRingLayered, pressable, raised } from './control-styles.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { showToast } from './toast.js';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';
import { translate } from './utils/labels.js';

export const DEFAULT_LABELS = {
    titleAdd: 'Add a cover',
    titleChange: 'Change the cover',
    currentHeading: 'Current cover',
    newHeading: 'New cover',
    noCoverTitle: 'This edition has no cover',
    noCoverIntro: 'Add one and it shows everywhere the book appears.',
    chooseHeading: 'Choose the new cover',
    chooseHeadingAdd: 'Choose a cover',
    replaces: 'Replaces the current cover',
    reasonHeading: 'Why are you replacing it?',
    reasonWrong: 'Wrong cover',
    reasonWrongHint: 'The image belongs to another edition or another book.',
    reasonBetter: 'Better image',
    reasonBetterHint: 'A sharper, cleaner, or more complete version of the same cover.',
    reasonNotFront: 'Not the front cover',
    reasonNotFrontHint: 'A back cover, spine, or a “no image” placeholder.',
    reasonOther: 'Something else',
    reasonNoteLabel: 'What’s wrong with the current cover?',
    reasonPrompt: 'Choose why you’re replacing it',
    images: 'Images',
    uploadTitle: 'Upload a new image',
    addHint: 'Drop a file here, paste, or browse',
    addHintTouch: 'Take a photo or choose a file',
    fileTypes: 'JPG, GIF, PNG or WebP, up to 10 MB.',
    paste: 'Paste image',
    errorClipboard: 'No image found on your clipboard.',
    dropHere: 'Drop the image to upload it',
    current: 'Current',
    sourceArchive: 'Scanned by Internet Archive',
    sourceWikidata: 'From Wikimedia Commons',
    sourceAmazon: 'From Amazon',
    titleCover: 'Cover',
    titleTitlePage: 'Title page',
    titlePhoto: 'Photo',
    titleUpload: 'Uploaded cover',
    titleYou: 'Your upload',
    detailJustNow: 'Just now',
    detailSize: '%(width)s × %(height)s px',
    detailId: 'Image %(id)s',
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
    { value: 'wrong', label: 'reasonWrong', hint: 'reasonWrongHint' },
    { value: 'better', label: 'reasonBetter', hint: 'reasonBetterHint' },
    { value: 'not_front', label: 'reasonNotFront', hint: 'reasonNotFrontHint' },
    { value: 'other', label: 'reasonOther' }
];

/** Matomo category for the dialog's funnel: Open, then Save (with its source and reason) or Close unsaved. */
const ANALYTICS = 'CoverManager';

const ACCEPT = '.jpg,.jpeg,.gif,.png,.webp,image/jpeg,image/gif,image/png,image/webp';
const IMAGE_TYPES = ['image/jpeg', 'image/gif', 'image/png', 'image/webp'];
const MAX_BYTES = 10 * 1024 * 1024;
const NOTE_MAX = 200;
const CAN_READ_CLIPBOARD = typeof navigator !== 'undefined' && typeof navigator.clipboard?.read === 'function';

/**
 * Picks and manages the images for a book, work, or author: every image
 * attached to it, plus suggestions that are always listed (Internet Archive
 * scans, Amazon's cover for the ISBN, a Wikidata photo). The cover column
 * shows the current image, or the one that will replace it. Once a
 * replacement is picked, a band under both columns shows the swap with a way
 * back and, when a book's own cover is being replaced, asks why. Adding a
 * spare image or removing an old one never asks. New images are added by drop,
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
        _reason: { state: true },
        _reasonNote: { state: true },
        _selected: { state: true },
        _removed: { state: true },
        _added: { state: true },
        _hidden: { state: true },
        _saving: { state: true },
        _dragging: { state: true },
        _error: { state: true },
        _wide: { state: true },
        _bandInView: { state: true }
    };

    static styles = [
        raised,
        pressable,
        focusRingLayered,
        css`
            :host {
                display: block;
                font-family: var(--font-family-body);
                color: var(--color-text);
                text-align: start;
            }

            /* minmax(0, …): a long caption must not widen the column past the dialog. */
            .layout {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: var(--spacing-xl);
            }

            /* --width-breakpoint-tablet */
            @media (min-width: 768px) {
                .layout {
                    grid-template-columns: minmax(180px, 2fr) minmax(0, 3fr);
                    align-items: start;
                }

                /* The preview stays put while a long list scrolls past it. */
                .cover {
                    position: sticky;
                    top: 0;
                }

                /* A record with nothing to show yet: the list is the whole dialog. */
                .layout.single {
                    grid-template-columns: minmax(0, 1fr);
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

            /* No fixed ratio: a cover keeps its own shape, so its caption sits right under it. */
            .cover-frame {
                display: grid;
                justify-items: start;
                overflow: hidden;
                border-radius: var(--border-radius-thumbnail);
            }

            .cover-frame.skeleton {
                aspect-ratio: 2 / 3;
            }

            /* Short enough that the preview and its caption fit a laptop viewport without scrolling. */
            .cover-frame img {
                display: block;
                max-width: 100%;
                max-height: min(420px, 44vh);
                object-fit: contain;
                box-shadow: var(--box-shadow-raised);
            }

            /* On a phone the cover sits beside its caption, so the list stays in view. */
            @media (max-width: 767px) {
                .cover-body {
                    display: grid;
                    grid-template-columns: 96px minmax(0, 1fr);
                    gap: var(--spacing-md);
                    align-items: start;
                }
            }

            /* With the band under it, the preview shrinks with the viewport so the sticky column,
               card included, still fits above the footer (about 624px of the height is everything else). */
            .cover.has-band .cover-frame img {
                max-height: clamp(120px, 100vh - 624px, 260px);
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

            /* The band, once a replacement is picked: the swap, then the question. Under the preview
               on wide screens, under the list on phones. The scroll margin keeps it clear of the sticky footer. */
            .band {
                display: grid;
                gap: var(--spacing-sm);
                margin-top: var(--spacing-lg);
                padding: var(--spacing-lg);
                border: var(--border-width-thin) solid var(--color-border-subtle);
                border-radius: var(--border-radius-card);
                background: var(--color-surface-sunken);
                scroll-margin-bottom: calc(var(--control-height-medium) + 2 * var(--spacing-lg) + var(--spacing-md));
            }

            .band-heading {
                margin: 0;
                font-size: var(--font-size-body-medium);
                font-weight: var(--font-weight-semibold);
                line-height: var(--line-height-meta);
            }

            .swap {
                display: flex;
                align-items: center;
                gap: var(--spacing-md);
            }

            .swap img {
                width: 48px;
                height: 72px;
                object-fit: cover;
                border-radius: var(--border-radius-sm);
                box-shadow: var(--box-shadow-raised);
            }

            .swap ol-icon {
                color: var(--color-text-secondary);
            }

            :host(:dir(rtl)) .swap ol-icon {
                transform: scaleX(-1);
            }

            .reason-heading {
                margin-top: var(--spacing-sm);
            }

            .why {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--spacing-sm) var(--spacing-md);
                min-width: 0;
            }

            .reason-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--spacing-xs);
                margin: 0;
                padding: 0;
                list-style: none;
            }

            /* A pressable pill, one per reason; the pressed one takes the control-selected look. */
            .chip {
                --control-surface: var(--color-control-bg);
                --control-highlight-strength: 60%;
                display: inline-flex;
                align-items: center;
                min-height: var(--control-height-small);
                padding: 0 var(--spacing-md);
                border: var(--border-width-thin) solid var(--color-control-border);
                border-radius: var(--border-radius-pill);
                background: var(--color-control-bg);
                color: var(--color-text);
                font-family: var(--font-family-button);
                font-size: var(--font-size-label-medium);
                font-weight: var(--font-weight-button);
                line-height: var(--line-height-control);
                cursor: pointer;
                box-sizing: border-box;
            }

            .chip[aria-pressed='true'] {
                --control-surface: var(--color-control-selected-surface);
                border-color: var(--color-control-selected-border);
                background: var(--color-control-selected-bg);
                color: var(--color-link);
            }

            .reason-hint {
                flex-basis: 100%;
                margin: 0;
                color: var(--color-text-secondary);
                font-size: var(--font-size-body-small);
                line-height: var(--line-height-body);
            }

            .note {
                flex-basis: 100%;
                display: flex;
                flex-direction: column;
                gap: var(--spacing-xs);
                margin: 0;
                font-size: var(--font-size-label-large);
                font-weight: var(--font-weight-medium);
            }

            /* 16px so iOS doesn't zoom on focus. */
            .note input {
                scroll-margin-bottom: calc(var(--control-height-medium) + 2 * var(--spacing-lg) + var(--spacing-md));
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

            /* The list side: a heading, then one row per image, the upload row first. */
            .step-title {
                margin: 0 0 var(--spacing-xs);
                font-family: var(--font-family-heading);
                font-size: var(--font-size-title-medium);
                font-weight: var(--font-weight-heading);
                line-height: var(--line-height-heading);
                text-wrap: balance;
            }

            .step-intro {
                margin: 0 0 var(--spacing-lg);
                color: var(--color-text-secondary);
                font-size: var(--font-size-body-medium);
                line-height: var(--line-height-body);
            }

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

            /* The whole upload row is the drop target, so the whole row wears the dashed edge. */
            .upload .option {
                border: var(--border-width-thick) dashed var(--color-border);
                background: var(--color-surface-raised);
            }

            .upload .thumb {
                background: var(--color-surface-sunken);
                color: var(--color-text-secondary);
            }

            /* Drawn like a native radio; the upload row keeps the space so thumbnails line up. */
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

            .meta > :is(.tag, .source, .detail) + :is(.source, .detail)::before {
                content: '·' / '';
                margin-inline-end: var(--spacing-xs);
            }

            /* A date or a size wraps as a whole, never "434 × 685" on one line and "px" on the next. */
            .meta .detail {
                white-space: nowrap;
            }

            .tag {
                font-weight: var(--font-weight-semibold);
            }

            /* Remove / Undo and the footer's reason link: quiet text links. */
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

                .option:hover:not(:disabled):not([aria-pressed='true']) {
                    background: var(--color-hover-overlay);
                    border-color: var(--color-border-muted);
                }

                .upload .option:hover {
                    border-color: var(--color-primary);
                    background: var(--color-primary-subtle);
                }

                .upload .option:hover .thumb {
                    color: var(--color-primary);
                }

                /* Border tracks the fill, as ol-button does; the pressed chip deepens its tint. */
                .chip:hover:not([aria-pressed='true']) {
                    --control-surface: var(--color-control-hover);
                    background: var(--color-control-hover);
                    border-color: var(--color-border-muted);
                }

                .chip[aria-pressed='true']:hover {
                    --control-surface: var(--color-control-selected-surface-hover);
                    background: var(--color-control-selected-bg-hover);
                    border-color: var(--color-control-selected-border-hover);
                }

                .text-action:hover {
                    text-decoration-thickness: 2px;
                }

                .row .text-action:not(.danger):hover {
                    color: var(--color-text);
                }

                /* One quiet Remove on the row under the pointer, not a red link on every row. */
                .row .text-action.danger {
                    opacity: 0;
                    color: var(--color-text-secondary);
                }

                .row:hover .text-action.danger,
                .row:focus-within .text-action.danger {
                    opacity: 1;
                }

                .row .text-action.danger:hover {
                    color: var(--color-error-fg);
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

            .status.error {
                margin: 0;
                padding: 0;
                border: 0;
                background: none;
                color: var(--color-error-fg);
            }

            .status .text-action {
                font-size: inherit;
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
                background: var(--color-skeleton);
                animation: pulse var(--duration-slower) var(--ease-in-out-cubic) infinite alternate;
            }

            .loading .cover-frame {
                width: min(100%, 240px);
                aspect-ratio: 2 / 3;
            }

            .skeleton-line {
                width: 40%;
                height: 12px;
                margin-bottom: var(--spacing-sm);
                border-radius: var(--border-radius-sm);
            }

            .skeleton-row {
                height: 102px;
                border-radius: var(--border-radius-card);
            }

            @media (max-width: 767px) {
                .loading .cover-frame {
                    width: 96px;
                }
            }

            .load-error {
                display: grid;
                justify-items: center;
                gap: var(--spacing-md);
                padding: var(--spacing-3xl) var(--spacing-lg);
                text-align: center;
            }

            .load-error ol-icon {
                color: var(--color-error-fg);
            }

            .load-error p {
                margin: 0;
                font-size: var(--font-size-body-medium);
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
        `
    ];

    constructor() {
        super();
        this.docKey = '';
        this.guidelinesUrl = '/help/faq/editing#picture';
        this.labels = {};
        this._data = null;
        this._loadState = 'idle';
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
        this._wideQuery = typeof matchMedia === 'function' ? matchMedia('(min-width: 768px)') : null;
        this._wide = Boolean(this._wideQuery?.matches);
        this._onWideChange = e => (this._wide = e.matches);
        this._bandInView = true;
        this._bandObserver = null;
        this._observedBand = null;
        this._onOpen = () => this.load();
        this._onClosed = e => {
            if (e.detail?.returnValue !== 'saved') this._trackClose();
            this._reset();
        };
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
        this._wideQuery?.addEventListener('change', this._onWideChange);
        // The whole dialog body takes drops, not just the list: people aim at the cover.
        this.addEventListener('dragenter', this._onDragEnter);
        this.addEventListener('dragover', this._onDragOver);
        this.addEventListener('dragleave', this._onDragLeave);
        this.addEventListener('drop', this._onDrop);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._wideQuery?.removeEventListener('change', this._onWideChange);
        this.removeEventListener('dragenter', this._onDragEnter);
        this.removeEventListener('dragover', this._onDragOver);
        this.removeEventListener('dragleave', this._onDragLeave);
        this.removeEventListener('drop', this._onDrop);
        this._bandObserver?.disconnect();
        this._observedBand = null;
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
            if (this._dialog) this._dialog.label = this._t(this._data.current ? 'titleChange' : 'titleAdd');
            this._loadState = 'ready';
            trackEvent(ANALYTICS, 'Open', this._openKind);
        } catch {
            this._loadState = 'error';
        }
    }

    /** What the dialog opened on: a photo, a cover to change, a scan shown in place of a cover, or nothing. */
    get _openKind() {
        if (this.docKey.startsWith('/authors/')) return 'photo';
        if (this._hasOwnImage) return 'change';
        return this._isFallback ? 'fallback' : 'add';
    }

    /** Where the saved cover came from: a suggestion's kind, a fresh upload, another attached image, or no change of cover. */
    _saveSource(selected) {
        if (selected.kind !== 'upload') return selected.kind;
        if (selected.session) return 'upload';
        return selected.id === this._data.current ? 'unchanged' : 'existing';
    }

    /** Closed without saving: untouched, stopped at the question, or left other changes unsaved. */
    _trackClose() {
        if (this._loadState !== 'ready') return;
        let label = 'unsaved';
        if (!this._isDirty) label = 'untouched';
        else if (this._needsReason && !this._reasonComplete) label = 'reason-pending';
        trackEvent(ANALYTICS, 'Close', label);
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

    /** The record has an image of its own; a scan shown in its place is a suggestion, not a cover. */
    get _hasOwnImage() {
        return Boolean(this._data?.current?.startsWith('img:'));
    }

    get _isFallback() {
        return Boolean(this._data?.current?.startsWith('suggestion:'));
    }

    /** Replacing a book's own cover asks why; adding a first cover or changing an author photo doesn't. */
    get _needsReason() {
        return this._hasOwnImage && !this.docKey.startsWith('/authors/') && this._selected !== this._data.current;
    }

    get _reasonComplete() {
        return Boolean(this._reason) && (this._reason !== 'other' || this._reasonNote.trim() !== '');
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

    get _canSave() {
        return this._isDirty && !this._added.some(item => item.pending) && (!this._needsReason || this._reasonComplete);
    }

    _isOpen() {
        return this._dialog ? this._dialog.open : this.isConnected;
    }

    _accepting() {
        return this._loadState === 'ready';
    }

    // The reason

    async _setReason(value) {
        this._reason = value;
        await this.updateComplete;
        if (value === 'other') this.shadowRoot.querySelector('.note input')?.focus();
    }

    /** Tracks whether the band is on screen, so the footer can point to the question when it isn't. */
    updated() {
        const band = this.shadowRoot.querySelector('.band');
        if (band === this._observedBand) return;
        this._bandObserver?.disconnect();
        this._observedBand = band;
        this._bandInView = true;
        if (!band || typeof IntersectionObserver !== 'function') return;
        // The bottom margin leaves out the strip the sticky footer covers.
        this._bandObserver = new IntersectionObserver(([entry]) => (this._bandInView = entry.intersectionRatio > 0.5), {
            rootMargin: '0px 0px -96px 0px',
            threshold: [0, 0.5, 1]
        });
        this._bandObserver.observe(band);
    }

    _scrollToBand() {
        this.shadowRoot.querySelector('.band')?.scrollIntoView({ block: 'end', behavior: 'smooth' });
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
        if (!this._canSave || this._saving) return;
        this._saving = true;
        this._error = '';
        // An image the record has is picked by id; a suggestion not copied in yet, by name.
        const selected = this._items.find(item => item.id === this._selected);
        const selection = selected.image_id ? { image_id: selected.image_id } : { suggestion: selected.suggestion };
        const reason = this._needsReason ? { reason: this._reason, ...(this._reason === 'other' ? { reason_note: this._reasonNote.trim() } : {}) } : {};
        try {
            const response = await fetch(`${this._endpoint}.json`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ ...selection, added: this._uploadedIds, removed: [...this._removed], ...reason })
            });
            if (!response.ok) throw new Error(response.statusText);
            const { cover_id: coverId } = await response.json();
            trackEvent(ANALYTICS, 'Save', this._saveSource(selected));
            if (reason.reason) trackEvent(ANALYTICS, 'Reason', reason.reason);
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
            trackEvent(ANALYTICS, 'SaveError');
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

    /** A row's title says what the image is; its meta line says where it came from. */
    _describe(item) {
        switch (item.kind) {
            case 'archive_cover':
                return { title: this._t('titleCover'), source: this._t('sourceArchive') };
            case 'archive_title':
                return { title: this._t('titleTitlePage'), source: this._t('sourceArchive') };
            case 'amazon':
                return { title: this._t('titleCover'), source: this._t('sourceAmazon') };
            case 'wikidata':
                return { title: this._t('titlePhoto'), source: this._t('sourceWikidata') };
            default: {
                if (item.session || item.pending) return { title: this._t('titleYou'), detail: this._t('detailJustNow') };
                const uploader = item.added_by?.name;
                const lang = document.documentElement.lang || 'en';
                const date = item.created ? new Intl.DateTimeFormat(lang, { month: 'long', year: 'numeric' }).format(new Date(item.created)) : '';
                const number = new Intl.NumberFormat(lang);
                const size = item.width && item.height ? this._t('detailSize', { width: number.format(item.width), height: number.format(item.height) }) : '';
                // With no uploader, date or size on file, the id still tells two images apart.
                const details = [date, size].filter(Boolean);
                const detail = details.length || uploader ? details : [this._t('detailId', { id: item.image_id })];
                return { title: this._t('titleUpload'), source: uploader, detail };
            }
        }
    }

    _name({ title, source, detail }) {
        return [title, source, ...[detail].flat()].filter(Boolean).join(', ');
    }

    _renderMeta({ source, detail }, tag) {
        if (!source && ![detail].flat().some(Boolean) && !tag) return nothing;
        return html`<span class="meta"
            >${tag ? html`<span class="tag">${tag}</span>` : nothing}${source ? html`<span class="source">${source}</span>` : nothing}${[detail]
                .flat()
                .filter(Boolean)
                .map(d => html`<span class="detail">${d}</span>`)}</span
        >`;
    }

    /** The image shown large: the selection, or the current cover while a selection is settling. */
    get _shown() {
        const items = this._items;
        return items.find(item => item.id === this._selected) ?? items.find(item => item.id === this._data?.current);
    }

    _renderCover(selected, band) {
        const current = this._items.find(item => item.id === this._data.current);
        const heading = selected === current ? 'currentHeading' : 'newHeading';
        const description = this._describe(selected);

        return html`<section class="cover ${band ? 'has-band' : ''}" aria-labelledby="cover-heading">
            <h3 class="overline" id="cover-heading">${this._t(heading)}</h3>
            <div class="cover-body">
                <div class="cover-frame"><img src=${selected.preview ?? selected.thumb} alt="" /></div>
                <div class="cover-caption">
                    <div class="text"><span class="title">${description.title}</span>${this._renderMeta(description)}</div>
                </div>
            </div>
            ${band ?? nothing}
        </section>`;
    }

    /** Once a replacement is picked: current → new, then the question if one is due.
        Under the preview on wide screens, so it stays in view beside the list; under the list on phones. */
    _renderBand(current, selected) {
        const asks = this._needsReason;
        return html`<div class="band">
            <strong class="band-heading">${this._t('replaces')}</strong>
            <div class="swap">
                <img src=${current.thumb} alt="" />
                <ol-icon name="arrow-right"></ol-icon>
                <img src=${selected.thumb} alt="" />
            </div>
            ${asks ? html`<h4 class="band-heading reason-heading" id="reason-heading">${this._t('reasonHeading')}</h4>` : nothing}
            ${asks ? this._renderReason() : nothing}
        </div>`;
    }

    _renderReason() {
        const chosen = REASONS.find(r => r.value === this._reason);
        return html`<div class="why" role="group" aria-labelledby="reason-heading">
            <ul class="reason-chips">
                ${REASONS.map(
                    ({ value, label }) =>
                        html`<li>
                            <button
                                class="chip raised pressable focus-ring-layered"
                                type="button"
                                data-value=${value}
                                aria-pressed=${this._reason === value ? 'true' : 'false'}
                                @click=${() => this._setReason(value)}
                            >
                                ${this._t(label)}
                            </button>
                        </li>`
                )}
            </ul>
            ${chosen?.hint ? html`<p class="reason-hint">${this._t(chosen.hint)}</p>` : nothing}
            ${
                this._reason === 'other'
                    ? html`<label class="note">
                          ${this._t('reasonNoteLabel')}
                          <input
                              type="text"
                              maxlength=${NOTE_MAX}
                              .value=${this._reasonNote}
                              @input=${e => (this._reasonNote = e.target.value)}
                              @keydown=${e => e.key === 'Enter' && this._save()}
                          />
                      </label>`
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

    _renderList() {
        let heading;
        if (this._data.current) heading = html`<h3 class="overline">${this._t('chooseHeading')}</h3>`;
        else if (this._shown) heading = html`<h3 class="overline">${this._t('chooseHeadingAdd')}</h3>`;
        else
            heading = html`<h3 class="step-title">${this._t('noCoverTitle')}</h3>
                <p class="step-intro">${this._t('noCoverIntro')}</p>`;
        return html`<div class="panel">
            ${heading}
            <div class="list-wrap">
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
        if (this._added.some(item => item.pending)) return this._t('uploading');
        if (!this._isDirty) return nothing;
        const parts = [];
        const newUploads = this._uploadedIds.filter(id => `img:${id}` !== this._selected).length;
        if (newUploads) parts.push(this._t('statusAdd', { count: newUploads }));
        if (this._removed.size) parts.push(this._t('statusRemove', { count: this._removed.size }));
        return parts.join(' ');
    }

    /** Errors sit in the footer, beside the button that caused them, where the sticky footer can't cover them. */
    _renderFooter() {
        let status;
        if (this._error) status = html`<p class="status error" role="alert"><ol-icon name="circle-alert" size="sm"></ol-icon>${this._error}</p>`;
        else if (this._needsReason && !this._reasonComplete && !this._bandInView)
            status = html`<p class="status"><button type="button" class="text-action" @click=${this._scrollToBand}>${this._t('reasonPrompt')}</button></p>`;
        else status = html`<p class="status" aria-live="polite">${this._renderStatus()}</p>`;
        return html`<div class="footer">
            ${status}
            <div class="actions">
                <a href=${this.guidelinesUrl} target="_blank" rel="noopener">${this._t('guidelines')}</a>
                <div class="buttons">
                    <ol-button variant="secondary" @click=${this._cancel}>${this._t('cancel')}</ol-button>
                    <ol-button variant="primary" ?disabled=${!this._canSave} ?loading=${this._saving} @click=${this._save}>${this._t('save')}</ol-button>
                </div>
            </div>
        </div>`;
    }

    render() {
        if (this._loadState === 'error') {
            return html`<div class="load-error" role="alert">
                <ol-icon name="circle-alert"></ol-icon>
                <p>${this._t('errorLoad')}</p>
                <div class="buttons">
                    <ol-button variant="secondary" @click=${this._cancel}>${this._t('cancel')}</ol-button>
                    <ol-button variant="primary" @click=${() => this.load()}>${this._t('retry')}</ol-button>
                </div>
            </div>`;
        }

        // Shaped like the loaded dialog (preview, then the upload row and three images), so nothing jumps when it arrives.
        if (this._loadState !== 'ready') {
            return html`<div class="layout loading" aria-busy="true" aria-label=${this._t('loading')}>
                <div class="cover">
                    <div class="skeleton skeleton-line"></div>
                    <div class="cover-body"><div class="cover-frame skeleton"></div></div>
                </div>
                <div class="panel">
                    <div class="skeleton skeleton-line"></div>
                    <div class="options">${[0, 1, 2, 3].map(() => html`<div class="skeleton skeleton-row"></div>`)}</div>
                </div>
            </div>`;
        }

        // With nothing to show yet, the list is the whole dialog; the cover column appears with the first pick.
        const shown = this._shown;
        const current = this._items.find(item => item.id === this._data.current);
        const band = current && shown && shown !== current ? this._renderBand(current, shown) : null;
        return html`
            <div class="layout ${shown ? '' : 'single'}">${shown ? this._renderCover(shown, this._wide ? band : null) : nothing} ${this._renderList()}</div>
            ${this._wide ? nothing : (band ?? nothing)} ${this._renderFooter()}
        `;
    }
}

customElements.define('ol-cover-manager', OlCoverManager);
