import { HardBreak } from '@tiptap/extension-hard-break';

/**
 * OLHardBreak – a hard-break node that serializes to OLMarkdown's dialect.
 *
 * The server-side display renderer (OLMarkdown, a vendored Python-Markdown)
 * treats every newline inside a paragraph as a `<br>` and has no escape syntax
 * for hard breaks. tiptap-markdown's default serializer emits CommonMark's
 * `\<newline>`; that trailing backslash makes OLMarkdown escape the `<` of the
 * `<br/>` it injects, so readers see the literal text `<br />`.
 *
 * Emitting a bare newline instead keeps the two renderers in agreement, and
 * re-saving a page through the editor cleans up any legacy backslash/`<br>`
 * cruft. See internetarchive/openlibrary#13074.
 */
export const OLHardBreak = HardBreak.extend({
    addStorage() {
        return {
            markdown: {
                serialize(state, node, parent, index) {
                    for (let i = index + 1; i < parent.childCount; i++) {
                        if (parent.child(i).type !== node.type) {
                            state.write('\n');
                            return;
                        }
                    }
                },
                parse: {
                    // handled by markdown-it
                },
            },
        };
    },
});
