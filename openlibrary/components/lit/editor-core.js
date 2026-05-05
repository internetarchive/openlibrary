/**
 * Heavy Tiptap/ProseMirror dependencies, loaded lazily by OLMarkdownEditor.
 * This module is code-split by Vite into its own chunk.
 */
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';
import Image from '@tiptap/extension-image';
import { HtmlBlock } from './html-block.js';

/**
 * Creates a configured Tiptap editor instance.
 * @param {Object} options
 * @param {HTMLElement} options.element - DOM element to mount the editor into
 * @param {string} options.content - Initial markdown content
 * @param {string} options.placeholder - Placeholder text when editor is empty
 * @param {Function} options.onUpdate - Called on every content change
 * @param {Function} options.onTransaction - Called on every transaction (for re-renders)
 * @param {boolean} [options.enableCode] - Enable inline code and fenced code blocks
 * @returns {Editor}
 */
export function createEditor({ element, content, placeholder, onUpdate, onTransaction, enableCode = false }) {
    return new Editor({
        element,
        extensions: [
            StarterKit.configure({
                heading: { levels: [1, 2, 3, 4] },
                codeBlock: enableCode ? undefined : false,
                code: enableCode ? undefined : false,
                link: { openOnClick: false, autolink: true },
                strike: false
            }),
            Markdown.configure({
                breaks: true,
                linkify: true
            }),
            Image.configure({
                inline: true,
                allowBase64: false,
            }),
            HtmlBlock,
            Placeholder.configure({ placeholder })
        ],
        content,
        onUpdate,
        onTransaction
    });
}
