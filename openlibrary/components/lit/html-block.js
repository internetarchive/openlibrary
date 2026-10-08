import { Node } from '@tiptap/core';

/**
 * HtmlBlock – a custom Tiptap node for raw HTML blocks.
 *
 * Preserves arbitrary HTML that doesn't map to standard editor nodes.
 * Shows the raw HTML source in an editable textarea.
 * Markdown round-trip: captures markdown-it `html_block` tokens on parse,
 * and outputs raw HTML on serialize.
 */
export const HtmlBlock = Node.create({
    name: 'htmlBlock',
    group: 'block',
    atom: true,

    addAttributes() {
        return {
            content: {
                default: '',
                parseHTML: (el) => {
                    const encoded = el.getAttribute('data-content');
                    if (encoded) {
                        try {
                            return decodeURIComponent(escape(atob(encoded)));
                        } catch {
                            return '';
                        }
                    }
                    return '';
                },
            },
        };
    },

    parseHTML() {
        return [{ tag: 'div[data-html-block]' }];
    },

    renderHTML({ node }) {
        const encoded = btoa(unescape(encodeURIComponent(node.attrs.content)));
        return ['div', { 'data-html-block': '', 'data-content': encoded }];
    },

    addNodeView() {
        return ({ node, getPos, editor }) => {
            const wrapper = document.createElement('div');
            wrapper.classList.add('html-block');

            const header = document.createElement('span');
            header.classList.add('html-block__label');
            header.textContent = '</> HTML';

            const source = document.createElement('textarea');
            source.classList.add('html-block__source');
            source.spellcheck = false;
            source.value = node.attrs.content;

            function autoSize() {
                source.style.height = 'auto';
                source.style.height = `${Math.max(40, source.scrollHeight)}px`;
            }

            // Commit changes to the node on blur
            source.addEventListener('blur', () => {
                const pos = getPos();
                if (typeof pos === 'number' && source.value !== node.attrs.content) {
                    editor.view.dispatch(
                        editor.view.state.tr.setNodeMarkup(pos, undefined, { content: source.value })
                    );
                }
            });

            source.addEventListener('input', autoSize);

            wrapper.appendChild(header);
            wrapper.appendChild(source);

            // Initial sizing after DOM insertion
            requestAnimationFrame(autoSize);

            return {
                dom: wrapper,
                update(updatedNode) {
                    if (updatedNode.type.name !== 'htmlBlock') return false;
                    node = updatedNode;
                    if (document.activeElement !== source) {
                        source.value = updatedNode.attrs.content;
                        autoSize();
                    }
                    return true;
                },
                stopEvent() { return true; },
                ignoreMutation() { return true; },
                destroy() {},
            };
        };
    },

    addCommands() {
        return {
            insertHtmlBlock: (content = '') => ({ commands }) => {
                return commands.insertContent({
                    type: this.name,
                    attrs: { content },
                });
            },
        };
    },

    addStorage() {
        return {
            markdown: {
                serialize(state, node) {
                    state.write(node.attrs.content.trim());
                    state.closeBlock(node);
                },
                parse: {
                    setup(markdownit) {
                        markdownit.renderer.rules.html_block = (tokens, idx) => {
                            const content = tokens[idx].content.trim();
                            const encoded = btoa(unescape(encodeURIComponent(content)));
                            return `<div data-html-block data-content="${encoded}"></div>`;
                        };
                    },
                },
            },
        };
    },
});
