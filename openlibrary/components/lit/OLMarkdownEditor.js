import { LitElement, html, css } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import './OlIcon.js';

/**
 * A WYSIWYG markdown editor built on Tiptap.
 *
 * Syncs its output to a hidden target element (textarea or input) identified by `target-id`.
 * The target element must exist in the DOM before the editor connects.
 *
 * @element ol-markdown-editor
 *
 * @prop {String} targetId - The ID of the DOM element to sync the Markdown output with.
 * @prop {String} placeholder - Text to display when the editor is empty (default: 'Write something...').
 * @prop {String} height - Minimum height of the editor area, e.g. '100px' (default: '200px'). The editor grows beyond this as content is added.
 *
 * @fires ol-markdown-editor-change - Dispatched whenever the editor content changes. `e.detail.value` contains the raw markdown string.
 *
 * @example
 * <textarea id="body-input">value</textarea>
 * <ol-markdown-editor target-id="body-input" placeholder="Type here..."></ol-markdown-editor>
 *
 * @example
 * <form action="/save" method="POST">
 *   <label for="page--body">Document Body:</label>
 *   <textarea id="page--body" name="body">**Initial** markdown.</textarea>
 *   <ol-markdown-editor target-id="page--body" placeholder="Write the main content..."></ol-markdown-editor>
 *   <button type="submit">Save Document</button>
 * </form>
 */

// Toolbar glyphs from the shared icon set, keyed by the editor's local names.
// .toolbar-btn ol-icon governs size and stroke width.
const glyph = (name) => html`<ol-icon name="${name}"></ol-icon>`;

const ICONS = {
    undo: glyph('undo'),
    redo: glyph('redo'),
    h1: glyph('heading-1'),
    h2: glyph('heading-2'),
    bold: glyph('bold'),
    italic: glyph('italic'),
    link: glyph('link'),
    save: glyph('check'),
    remove: glyph('trash'),
    quote: glyph('quote'),
    hr: glyph('minus'),
    ul: glyph('list'),
    ol: glyph('list-ordered'),
    image: glyph('image'),
    code: glyph('code'),
    codeInline: glyph('braces'),
    codeBlock: glyph('square-code'),
    more: glyph('ellipsis'),
    source: glyph('file-code'),
};

export class OLMarkdownEditor extends LitElement {
    static properties = {
        targetId: { type: String, attribute: 'target-id' },
        placeholder: { type: String },
        height: { type: String },
        editor: { state: true },
        showLinkPopover: { state: true },
        linkInputValue: { state: true },
        showImagePopover: { state: true },
        imageUrlValue: { state: true },
        _errorMsg: { state: true },
        showOverflowMenu: { state: true },
        showSource: { state: true },
        enableHtmlBlock: { type: Boolean, attribute: 'enable-html-block' },
        enableCode: { type: Boolean, attribute: 'enable-code' }
    };

    static styles = css`
    :host {
      display: block;
      /* As a flex/grid item, an unbreakable code line must not set the
         minimum width — the pre scrolls instead of widening the host. */
      min-width: 0;
      max-width: 100%;
    }

    .loading-placeholder {
      color: var(--color-text-muted);
      pointer-events: none;
    }

    .editor-wrapper {
      border: var(--border-input);
      border-radius: var(--border-radius-card);
      background: var(--white);
      color: var(--color-text);
      max-height: 70vh;
      overflow-y: auto;
      /* Contain the toolbar/popover layering — a shadow root is not a
         stacking context, so without this their z-index leaks to the page. */
      isolation: isolate;
    }

    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: var(--spacing-inline-sm);
      padding: var(--spacing-inset-xs);
      border-bottom: var(--border-card);
      border-radius: var(--border-radius-card) var(--border-radius-card) 0 0;
      background: var(--color-surface-header);
      align-items: center;
      position: sticky;
      top: 0;
      /* Above the editor content; the popovers below are its descendants. */
      z-index: var(--z-index-local-1);
    }

    .toolbar-divider {
      height: var(--spacing-xl);
      margin: 0 var(--spacing-inline-sm);
      border-left: var(--border-divider);
    }

    .editor-input {
      padding: var(--spacing-inset-sm);
      min-height: 200px;
      display: flex;
      flex-direction: column;
      cursor: text;
    }

    .editor-input .tiptap {
      outline: none;
      flex-grow: 1;
      font-family: var(--font-family-body);
      font-size: var(--font-size-body, 0.875rem);
      line-height: var(--line-height-body);
    }

    .editor-input .tiptap h1 {
      font-size: var(--font-size-h1, 1.5rem);
      margin: 0 0 0.5em;
    }

    .editor-input .tiptap h2 {
      font-size: var(--font-size-h2, 1.25rem);
      margin: 0 0 0.45em;
    }

    .editor-input .tiptap p {
      margin: 0 0 0.55em;
    }

    .editor-input .tiptap ul,
    .editor-input .tiptap ol {
      margin: 0 0 0.55em;
    }

    .editor-input .tiptap a {
      color: var(--color-link);
    }

    .editor-input .tiptap img {
      max-width: 100%;
      height: auto;
      border-radius: var(--border-radius-card);
    }

    .editor-input .tiptap img.ProseMirror-selectednode {
      outline: var(--focus-width) solid var(--color-border-focused);
    }

    .html-block {
      border: 1px dashed var(--color-border-muted);
      border-radius: var(--border-radius-card);
      margin: 0.55em 0;
      overflow: hidden;
    }

    .html-block__label {
      display: block;
      padding: 4px 8px;
      background: var(--color-surface-header);
      border-bottom: 1px dashed var(--color-border-muted);
      font-size: 0.7rem;
      font-family: monospace;
      font-weight: 600;
      color: var(--color-text);
    }

    .html-block__source {
      display: block;
      width: 100%;
      border: none;
      padding: 8px;
      font-family: monospace;
      font-size: 0.8rem;
      resize: vertical;
      min-height: 40px;
      box-sizing: border-box;
      outline: none;
      background: var(--color-surface-sunken);
    }

    .editor-input .tiptap blockquote {
      margin-left: var(--spacing-lg);
      padding: var(--spacing-sm) var(--spacing-lg);
      border-left: var(--border-width-thick) solid var(--color-border-subtle);
      color: var(--color-text);
      background: var(--color-surface-sunken);
      font-style: italic;
      font-family: var(--font-family-body);
    }

    .editor-input .tiptap blockquote p {
      margin: 0;
    }

    .editor-input .tiptap code {
      background: var(--color-surface-sunken);
      border: 1px solid var(--color-border-subtle);
      border-radius: var(--border-radius-input);
      padding: 0.1em 0.3em;
      font-family: monospace;
      font-size: 0.85em;
    }

    .editor-input .tiptap pre {
      background: var(--color-surface-sunken);
      border: 1px solid var(--color-border-subtle);
      border-radius: var(--border-radius-card);
      padding: var(--spacing-inset-sm);
      margin: 0 0 0.55em;
      overflow-x: auto;
      font-family: monospace;
      font-size: 0.85em;
    }

    .editor-input .tiptap pre code {
      background: none;
      border: none;
      padding: 0;
      font-size: inherit;
    }

    .tiptap p.is-editor-empty:first-child::before {
      color: var(--color-text-muted);
      content: attr(data-placeholder);
      float: left;
      height: 0;
      pointer-events: none;
    }

    .toolbar-btn {
      background: transparent;
      border: var(--border-width-none);
      border-radius: var(--border-radius-button);
      padding: var(--spacing-inset-xs);
      cursor: pointer;
      color: var(--color-text);
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .toolbar-btn ol-icon { width: var(--spacing-xl); height: var(--spacing-xl); --ol-icon-stroke-width: 2.2; }

    @media (hover: hover) and (pointer: fine) {
      .toolbar-btn:hover:not(:disabled) { background: var(--color-hover-overlay); }
    }

    .toolbar-btn:active:not(:disabled) { transform: scale(var(--press-scale-compact)); }

    /* Pressed toolbar button = a selected control; same fill as ol-button[selected]. */
    .toolbar-btn.is-active {
      background: var(--color-control-selected-bg);
      color: var(--color-link);
    }

    .toolbar-btn:focus-visible {
      outline: var(--focus-width) solid var(--color-focus-ring);
      outline-offset: -2px;
    }

    .toolbar-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    .link-popover-wrapper { position: relative; display: inline-flex; }

    .link-popover {
      position: absolute;
      top: calc(100% + var(--spacing-xs));
      border: var(--border-overlay);
      border-radius: var(--border-radius-overlay);
      padding: var(--spacing-inset-xs);
      box-shadow: var(--box-shadow-overlay);
      background: var(--white);
      display: flex;
      gap: var(--spacing-inline-md);
      min-width: 260px;
      z-index: var(--z-index-local-1);
    }

    @media (max-width: 767px) {
      .link-popover-wrapper { position: static; }
      .link-popover {
        left: var(--spacing-inset-xs);
        right: var(--spacing-inset-xs);
        min-width: auto;
      }
    }

    .link-input {
      flex-grow: 1;
      border: var(--border-input);
      border-radius: var(--border-radius-input);
      padding: var(--spacing-xs) var(--spacing-md);
      outline: none;
      transition: border-color var(--duration-fast) var(--ease-state);
      font-family: var(--font-family-body);
    }

    @media (prefers-reduced-motion: reduce) {
      .link-input {
        transition: none;
      }
    }

    .link-input:focus {
      border: var(--border-input-focused);
      box-shadow: var(--box-shadow-focus);
    }

    /* iOS zooms in on focus when the input font is < 16px; bump it up on
       mobile to suppress that. */
    @media (max-width: 767px) {
      .link-input { font-size: var(--font-size-body-large); }
    }

    .error-state {
      padding: var(--spacing-inset-sm);
      border: var(--border-width-control) solid var(--color-border-error);
      background: var(--color-error-bg);
      color: var(--color-error-fg);
      border-radius: var(--border-radius-notification);
      font-family: var(--font-family-body);
      margin-bottom: var(--spacing-stack-sm);
    }

    .overflow-secondary {
      display: contents;
    }

    .toolbar-right-slot {
      display: contents;
    }

    .toolbar-formatting {
      display: contents;
    }

    .toolbar-formatting[inert] .toolbar-btn {
      opacity: 0.4;
    }

    .toolbar-spacer {
      flex: 1 1 auto;
    }

    .source-textarea {
      display: block;
      width: 100%;
      box-sizing: border-box;
      min-height: 200px;
      padding: var(--spacing-inset-sm);
      border: var(--border-width-none);
      border-radius: 0 0 var(--border-radius-card) var(--border-radius-card);
      background: var(--white);
      color: var(--color-text);
      font-family: monospace;
      font-size: 0.75rem;
      line-height: 1.5;
      resize: vertical;
      outline: none;
    }

    .editor-input.is-hidden {
      display: none;
    }

    .overflow-menu-wrapper { position: relative; display: inline-flex; }
    .overflow-menu-wrapper.overflow-toggle { display: none; }

    .overflow-menu {
      position: absolute;
      top: calc(100% + var(--spacing-xs));
      right: 0;
      border: var(--border-overlay);
      border-radius: var(--border-radius-overlay);
      padding: var(--spacing-inset-xs);
      box-shadow: var(--box-shadow-overlay);
      background: var(--white);
      display: flex;
      gap: var(--spacing-inline-sm);
      z-index: var(--z-index-local-1);
    }

    @media (max-width: 767px) {
      .overflow-secondary { display: none; }
      .overflow-menu-wrapper.overflow-toggle { display: inline-flex; }
    }
  `;

    constructor() {
        super();
        this.editor = null;
        this.targetElement = null;
        this.showLinkPopover = false;
        this.linkInputValue = '';
        this.showImagePopover = false;
        this.imageUrlValue = '';
        this._errorMsg = null;
        this.showOverflowMenu = false;
        this.showSource = false;
        this._handleDocumentClick = this._handleDocumentClick.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('mousedown', this._handleDocumentClick);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('mousedown', this._handleDocumentClick);

        if (this.targetElement) {
            this.targetElement.style.display = '';
            if (this._associatedLabel && this._labelClickHandler) {
                this._associatedLabel.removeEventListener('click', this._labelClickHandler);
            }
        }

        if (this.editor) this.editor.destroy();
    }

    _handleDocumentClick(e) {
        if (!this.showLinkPopover && !this.showImagePopover && !this.showOverflowMenu) return;
        if (!e.composedPath().includes(this)) {
            this.showLinkPopover = false;
            this.showImagePopover = false;
            this.showOverflowMenu = false;
        }
    }

    async firstUpdated() {
        if (!this.targetId) {
            this._errorMsg = 'Missing \'target-id\' attribute.';
            throw new Error(`OLMarkdownEditor: ${this._errorMsg}`);
        }

        this.targetElement = document.getElementById(this.targetId);

        if (!this.targetElement) {
            this._errorMsg = `Target element with ID "${this.targetId}" not found in the DOM.`;
            throw new Error(`OLMarkdownEditor: ${this._errorMsg}`);
        }

        const { createEditor } = await import('./editor-core.js');

        const initialContent = this.targetElement.value || '';
        const editorRoot = this.shadowRoot.getElementById('editor-root');

        this.editor = createEditor({
            element: editorRoot,
            content: initialContent,
            placeholder: this.placeholder || 'Write something...',
            enableCode: this.enableCode,
            onUpdate: ({ editor }) => {
                let markdownOutput = editor.storage.markdown.getMarkdown();

                // Note, tiptap uses 2 spaces for list indentation, olmarkdown uses 4.
                // Normalize nested list indentation from 2-space-per-level (tiptap) to
                // 4-space-per-level (olmarkdown) without injecting extra newlines.
                markdownOutput = markdownOutput.replace(
                    /^(\s{2,})([*+-]|\d+\.) /gm,
                    (match, spaces, marker) => {
                        const depth = Math.round(spaces.length / 2);
                        const newIndent = ' '.repeat(depth * 4);
                        return `${newIndent}${marker} `;
                    }
                );

                if (this.targetElement) {
                    this.targetElement.value = markdownOutput;
                }

                this.dispatchEvent(new CustomEvent('ol-markdown-editor-change', {
                    detail: { value: markdownOutput },
                    bubbles: true,
                    composed: true
                }));
            },
            onTransaction: () => {
                this.requestUpdate();
            }
        });

        this.targetElement.style.display = 'none';

        const associatedLabel = document.querySelector(`label[for="${this.targetId}"]`);
        if (associatedLabel) {
            this._associatedLabel = associatedLabel;
            this._labelClickHandler = (e) => {
                e.preventDefault();
                this._focusEditor();
            };
            associatedLabel.addEventListener('click', this._labelClickHandler);
        }
    }

    _handleToolbarMouseDown(e) {
        if (!e.target.closest('.toolbar-btn')) e.preventDefault();
    }

    /**
     * Escape closes the overflow menu and returns focus to its trigger, which
     * would otherwise be removed from the DOM under the user's focus. Scoped to
     * the menu's wrapper — the link and image inputs handle their own Escape.
     */
    _handleOverflowKeydown(e) {
        if (e.key !== 'Escape' || !this.showOverflowMenu) return;
        e.stopPropagation();
        this.showOverflowMenu = false;
        this.updateComplete.then(() => {
            this.shadowRoot.querySelector('.overflow-menu-wrapper .toolbar-btn')?.focus();
        });
    }

    _focusEditor(e) {
        if (!this.editor) return;
        if (e && e.target.closest('.html-block')) return;
        if (!this.editor.isFocused) this.editor.commands.focus();
    }

    formatHeading(level) { if (!this.editor) return; this.editor.chain().focus().toggleHeading({ level }).run(); }
    formatText(type) { if (!this.editor) return; this.editor.chain().focus()[`toggle${type.charAt(0).toUpperCase() + type.slice(1)}`]().run(); }
    insertRule() { if (!this.editor) return; this.editor.chain().focus().setHorizontalRule().run(); }
    insertHtmlBlock() { if (!this.editor) return; this.editor.commands.insertHtmlBlock(''); }
    formatQuote() { if (!this.editor) return; this.editor.chain().focus().toggleBlockquote().run(); }
    formatInlineCode() { if (!this.editor) return; this.editor.chain().focus().toggleCode().run(); }
    formatCodeBlock() { if (!this.editor) return; this.editor.chain().focus().toggleCodeBlock().run(); }
    formatList(type) { if (!this.editor) return; this.editor.chain().focus()[type === 'bullet' ? 'toggleBulletList' : 'toggleOrderedList']().run(); }

    toggleLinkPopover() {
        if (!this.editor) return;
        this.showLinkPopover = !this.showLinkPopover;
        if (this.showLinkPopover) {
            this.showOverflowMenu = false;
            this.linkInputValue = this.editor.getAttributes('link').href || '';
            setTimeout(() => this.shadowRoot.querySelector('.link-input')?.focus(), 0);
        }
    }

    handleLinkInput(e) { this.linkInputValue = e.target.value; }

    handleLinkKeydown(e) {
        if (e.key === 'Enter') { e.preventDefault(); this.applyLink(); }
        if (e.key === 'Escape') { this.showLinkPopover = false; this._focusEditor(); }
    }

    applyLink() {
        if (!this.editor) return;
        const chain = this.editor.chain().focus().extendMarkRange('link');
        this.linkInputValue === '' ? chain.unsetLink().run() : chain.setLink({ href: this.linkInputValue }).run();
        this.showLinkPopover = false;
    }

    removeLink() {
        if (!this.editor) return;
        this.editor.chain().focus().extendMarkRange('link').unsetLink().run();
        this.showLinkPopover = false;
    }

    // Image popover
    toggleImagePopover() {
        if (!this.editor) return;
        this.showImagePopover = !this.showImagePopover;
        if (this.showImagePopover) {
            this.showLinkPopover = false;
            this.showOverflowMenu = false;
            this.imageUrlValue = '';
            setTimeout(() => this.shadowRoot.querySelector('.image-input')?.focus(), 0);
        }
    }

    handleImageInput(e) { this.imageUrlValue = e.target.value; }

    handleImageKeydown(e) {
        if (e.key === 'Enter') { e.preventDefault(); this.applyImage(); }
        if (e.key === 'Escape') { this.showImagePopover = false; this._focusEditor(); }
    }

    applyImage() {
        if (!this.editor || !this.imageUrlValue) return;
        this.editor.chain().focus().setImage({ src: this.imageUrlValue }).run();
        this.showImagePopover = false;
    }

    _isActive(type, options = {}) {
        return this.editor ? this.editor.isActive(type, options) : false;
    }

    _toggleSource() {
        if (!this.editor) return;
        if (this.showSource) {
            const textarea = this.shadowRoot.querySelector('.source-textarea');
            if (textarea) {
                const newValue = textarea.value;
                if (this.targetElement) this.targetElement.value = newValue;
                this.editor.commands.setContent(newValue, false);
            }
            this.showSource = false;
            this.showLinkPopover = false;
            this.showImagePopover = false;
            this.showOverflowMenu = false;
            this.updateComplete.then(() => this._focusEditor());
        } else {
            // Capture the editor's current height so the textarea doesn't jump.
            const editorRoot = this.shadowRoot.getElementById('editor-root');
            this._sourceModeHeight = editorRoot ? `${editorRoot.offsetHeight}px` : null;
            this.showSource = true;
            this.showLinkPopover = false;
            this.showImagePopover = false;
            this.showOverflowMenu = false;
            this.updateComplete.then(() => {
                this.shadowRoot.querySelector('.source-textarea')?.focus();
            });
        }
    }

    _handleSourceInput(e) {
        if (this.targetElement) this.targetElement.value = e.target.value;
        this.dispatchEvent(new CustomEvent('ol-markdown-editor-change', {
            detail: { value: e.target.value },
            bubbles: true,
            composed: true
        }));
    }

    /**
     * `isPressed` defaults to `isActive` so plain format toggles need nothing
     * extra; pass `null` for a disclosure trigger, where `aria-pressed` would
     * claim a formatting state the button doesn't have. `isExpanded` marks the
     * button as a disclosure and reflects whether its panel is open.
     */
    _renderButton({ title, icon, action, isActive = false, isDisabled = false, customColor = null, isPressed = isActive, isExpanded = null }) {
        const isBtnDisabled = !this.editor || isDisabled;

        return html`
      <button
        type="button"
        title="${title}"
        aria-label="${title}"
        aria-pressed="${ifDefined(isPressed === null ? undefined : isPressed)}"
        aria-expanded="${ifDefined(isExpanded === null ? undefined : isExpanded)}"
        class="toolbar-btn ${isActive ? 'is-active' : ''}"
        style="${customColor ? `color: ${customColor};` : ''}"
        @click="${action}"
        ?disabled="${isBtnDisabled}"
      >
        ${icon}
      </button>
    `;
    }

    render() {
        if (this._errorMsg) {
            return html`
                <div class="error-state">
                    <strong>Editor Initialization Failed:</strong> ${this._errorMsg}<br>
                    <small>The standard text input has been kept active as a fallback.</small>
                </div>
            `;
        }

        const secondaryButtons = html`
          ${this._renderButton({ title: 'Heading 1', icon: ICONS.h1, action: () => this.formatHeading(1), isActive: this._isActive('heading', { level: 1 }) })}
          ${this._renderButton({ title: 'Heading 2', icon: ICONS.h2, action: () => this.formatHeading(2), isActive: this._isActive('heading', { level: 2 }) })}
          ${this._renderButton({ title: 'Image', icon: ICONS.image, action: () => { this.showOverflowMenu = false; this.toggleImagePopover(); }, isActive: this.showImagePopover })}
          ${this._renderButton({ title: 'Blockquote', icon: ICONS.quote, action: this.formatQuote.bind(this), isActive: this._isActive('blockquote') })}
          ${this._renderButton({ title: 'Divider', icon: ICONS.hr, action: this.insertRule.bind(this) })}
          ${this.enableCode ? this._renderButton({ title: 'Inline Code', icon: ICONS.codeInline, action: this.formatInlineCode.bind(this), isActive: this._isActive('code') }) : ''}
          ${this.enableCode ? this._renderButton({ title: 'Code Block', icon: ICONS.codeBlock, action: this.formatCodeBlock.bind(this), isActive: this._isActive('codeBlock') }) : ''}
          ${this.enableHtmlBlock ? this._renderButton({ title: 'HTML Block', icon: ICONS.code, action: this.insertHtmlBlock.bind(this) }) : ''}
          ${!this.showSource ? this._renderButton({ title: 'View source', icon: ICONS.source, action: () => { this.showOverflowMenu = false; this._toggleSource(); } }) : ''}
        `;

        return html`
      <div class="editor-wrapper">
        <div class="toolbar" @mousedown="${this._handleToolbarMouseDown}">
          <div class="toolbar-formatting" ?inert="${this.showSource}">
            ${this._renderButton({ title: 'Undo', icon: ICONS.undo, action: () => this.editor.chain().focus().undo().run(), isDisabled: !this.editor || !this.editor.can().undo() })}
            ${this._renderButton({ title: 'Redo', icon: ICONS.redo, action: () => this.editor.chain().focus().redo().run(), isDisabled: !this.editor || !this.editor.can().redo() })}
            <div class="toolbar-divider overflow-secondary"></div>
            <span class="overflow-secondary">
              ${this._renderButton({ title: 'Heading 1', icon: ICONS.h1, action: () => this.formatHeading(1), isActive: this._isActive('heading', { level: 1 }) })}
              ${this._renderButton({ title: 'Heading 2', icon: ICONS.h2, action: () => this.formatHeading(2), isActive: this._isActive('heading', { level: 2 }) })}
            </span>
            <div class="toolbar-divider"></div>
            ${this._renderButton({ title: 'Bold', icon: ICONS.bold, action: () => this.formatText('bold'), isActive: this._isActive('bold') })}
            ${this._renderButton({ title: 'Italic', icon: ICONS.italic, action: () => this.formatText('italic'), isActive: this._isActive('italic') })}
            <div class="link-popover-wrapper">
              ${this._renderButton({ title: 'Link', icon: ICONS.link, action: this.toggleLinkPopover.bind(this), isActive: this._isActive('link') || this.showLinkPopover, isPressed: this._isActive('link'), isExpanded: this.showLinkPopover })}
              ${this.showLinkPopover ? html`
                <div class="link-popover" @mousedown="${(e) => e.stopPropagation()}">
                  <input type="url" class="link-input" placeholder="https://..." .value="${this.linkInputValue}" @input="${this.handleLinkInput}" @keydown="${this.handleLinkKeydown}" />
                  ${this._renderButton({ title: 'Save Link', icon: ICONS.save, action: this.applyLink.bind(this) })}
                  ${this._isActive('link') ? this._renderButton({ title: 'Remove Link', icon: ICONS.remove, action: this.removeLink.bind(this), customColor: 'var(--color-destructive)' }) : ''}
                </div>
              ` : ''}
            </div>
            <div class="link-popover-wrapper">
              <span class="overflow-secondary">
                ${this._renderButton({ title: 'Image', icon: ICONS.image, action: this.toggleImagePopover.bind(this), isActive: this.showImagePopover, isPressed: null, isExpanded: this.showImagePopover })}
              </span>
              ${this.showImagePopover ? html`
                <div class="link-popover" @mousedown="${(e) => e.stopPropagation()}">
                  <input type="url" class="link-input image-input" placeholder="https://..." .value="${this.imageUrlValue}" @input="${this.handleImageInput}" @keydown="${this.handleImageKeydown}" />
                  ${this._renderButton({ title: 'Insert Image', icon: ICONS.save, action: this.applyImage.bind(this) })}
                </div>
              ` : ''}
            </div>
            <div class="toolbar-divider"></div>
            ${this._renderButton({ title: 'Bullet List', icon: ICONS.ul, action: () => this.formatList('bullet'), isActive: this._isActive('bulletList') })}
            ${this._renderButton({ title: 'Numbered List', icon: ICONS.ol, action: () => this.formatList('number'), isActive: this._isActive('orderedList') })}
            <div class="toolbar-divider"></div>
            <span class="overflow-secondary">
              ${this._renderButton({ title: 'Blockquote', icon: ICONS.quote, action: this.formatQuote.bind(this), isActive: this._isActive('blockquote') })}
              ${this._renderButton({ title: 'Divider', icon: ICONS.hr, action: this.insertRule.bind(this) })}
              ${this.enableCode ? this._renderButton({ title: 'Inline Code', icon: ICONS.codeInline, action: this.formatInlineCode.bind(this), isActive: this._isActive('code') }) : ''}
              ${this.enableCode ? this._renderButton({ title: 'Code Block', icon: ICONS.codeBlock, action: this.formatCodeBlock.bind(this), isActive: this._isActive('codeBlock') }) : ''}
              ${this.enableHtmlBlock ? this._renderButton({ title: 'HTML Block', icon: ICONS.code, action: this.insertHtmlBlock.bind(this) }) : ''}
            </span>
            <div class="overflow-menu-wrapper overflow-toggle" @keydown="${this._handleOverflowKeydown}">
              ${this._renderButton({ title: 'More', icon: ICONS.more, action: () => { this.showOverflowMenu = !this.showOverflowMenu; if (this.showOverflowMenu) this.showLinkPopover = false; }, isActive: this.showOverflowMenu, isPressed: null, isExpanded: this.showOverflowMenu })}
              ${this.showOverflowMenu ? html`
                <div class="overflow-menu" @mousedown="${(e) => e.stopPropagation()}">
                  ${secondaryButtons}
                </div>
              ` : ''}
            </div>
          </div>
          <span class="${this.showSource ? 'toolbar-right-slot' : 'overflow-secondary'}">
            <div class="toolbar-spacer"></div>
            <div class="toolbar-divider"></div>
            ${this._renderButton({ title: this.showSource ? 'View formatted' : 'View source', icon: ICONS.source, action: this._toggleSource.bind(this), isActive: this.showSource })}
          </span>
        </div>

        <div id="editor-root" class="editor-input ${this.showSource ? 'is-hidden' : ''}" style="${this.height ? `min-height:${this.height}` : ''}" @click="${this._focusEditor}">
            ${!this.editor ? html`<span class="loading-placeholder">${this.placeholder || 'Write something...'}</span>` : ''}
        </div>
        ${this.showSource ? html`
          <textarea
            class="source-textarea"
            spellcheck="false"
            style="min-height:${this._sourceModeHeight || this.height || '200px'}"
            .value="${this.targetElement?.value || ''}"
            @input="${this._handleSourceInput}"
          ></textarea>
        ` : ''}
      </div>
    `;
    }
}

customElements.define('ol-markdown-editor', OLMarkdownEditor);
