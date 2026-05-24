/**
 * Round-trip tests for the WYSIWYG markdown editor.
 *
 * The editor's critical contract: existing markdown content loaded from the
 * database must survive a load→save cycle without corruption.  These tests
 * feed markdown into a Tiptap editor configured identically to editor-core.js,
 * read it back via tiptap-markdown, apply the same post-processing as
 * OLMarkdownEditor, and compare.
 */

import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Image from '@tiptap/extension-image';
import { HtmlBlock } from '../../../openlibrary/components/lit/html-block.js';

/* ------------------------------------------------------------------ */
/*  Helper: create an editor identical to production, roundtrip text   */
/* ------------------------------------------------------------------ */

function createTestEditor(markdownContent, { enableCode = false } = {}) {
    const el = document.createElement('div');
    document.body.appendChild(el);

    const editor = new Editor({
        element: el,
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
        ],
        content: markdownContent,
    });

    return { editor, el };
}

/**
 * Apply the same post-processing that OLMarkdownEditor.onUpdate does:
 * normalize 2-space list indentation to 4-space.
 */
function postProcessMarkdown(md) {
    return md.replace(
        /^(\s{2,})([*+-]|\d+\.) /gm,
        (match, spaces, marker) => {
            const depth = Math.round(spaces.length / 2);
            const newIndent = ' '.repeat(depth * 4);
            return `${newIndent}${marker} `;
        }
    );
}

/**
 * Full round-trip: markdown → editor → markdown (with post-processing).
 */
function roundTrip(input, options) {
    const { editor, el } = createTestEditor(input, options);
    const raw = editor.storage.markdown.getMarkdown();
    const output = postProcessMarkdown(raw);
    editor.destroy();
    el.remove();
    return output;
}

/**
 * Normalize whitespace for comparison: trim lines, collapse blank lines,
 * strip trailing whitespace. We care about *semantic* equivalence, not
 * exact byte-for-byte match (trailing spaces, trailing newlines, etc.).
 */
function normalize(md) {
    return md
        .replace(/\r\n/g, '\n')
        .split('\n')
        .map(l => l.trimEnd())
        .join('\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

/* ================================================================== */
/*  TESTS                                                              */
/* ================================================================== */

describe('OLMarkdownEditor markdown round-trip', () => {

    /* ---------- plain text ---------- */

    test('plain paragraph survives round-trip', () => {
        const input = 'Hello world, this is a simple paragraph.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    test('multiple paragraphs survive round-trip', () => {
        const input = 'First paragraph.\n\nSecond paragraph.\n\nThird paragraph.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    /* ---------- inline formatting ---------- */

    test('bold text survives round-trip', () => {
        const input = 'This is **bold** text.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    test('italic text survives round-trip', () => {
        const input = 'This is *italic* text.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    test('bold and italic combined survive round-trip', () => {
        const input = 'This is ***bold and italic*** text.';
        const output = normalize(roundTrip(input));
        // The serializer may reorder markers; check semantic equivalence
        expect(output).toMatch(/bold and italic/);
        expect(output).toMatch(/\*{1,3}bold and italic\*{1,3}/);
    });

    test('underscore bold survives (may convert to asterisks)', () => {
        const input = 'This is __bold__ text.';
        const output = normalize(roundTrip(input));
        // tiptap-markdown may normalize to ** - that's fine
        expect(output).toContain('bold');
        expect(output).toMatch(/(\*\*|__)bold(\*\*|__)/);
    });

    test('underscore italic survives (may convert to asterisks)', () => {
        const input = 'This is _italic_ text.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('italic');
        expect(output).toMatch(/(\*|_)italic(\*|_)/);
    });

    /* ---------- headings ---------- */

    test('heading level 1 survives round-trip', () => {
        const input = '# Heading One\n\nSome text.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    test('heading level 2 survives round-trip', () => {
        const input = '## Heading Two\n\nSome text.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    test('heading level 3 survives round-trip', () => {
        const input = '### Heading Three\n\nSome text.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    test('heading level 4 survives round-trip', () => {
        const input = '#### Heading Four\n\nSome text.';
        expect(normalize(roundTrip(input))).toBe(normalize(input));
    });

    test('heading level 5 is downgraded (only h1-h4 supported)', () => {
        const input = '##### Heading Five';
        const output = normalize(roundTrip(input));
        expect(output).not.toMatch(/^#####/m);
        expect(output).toContain('Heading Five');
    });

    /* ---------- links ---------- */

    test('inline link survives round-trip', () => {
        const input = 'Visit [OpenLibrary](https://openlibrary.org) for books.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('[OpenLibrary](https://openlibrary.org)');
    });

    test('bare URL is preserved', () => {
        const input = 'Check https://openlibrary.org for details.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('https://openlibrary.org');
    });

    test('link with title survives (title may be lost)', () => {
        const input = 'See [OL](https://openlibrary.org "Open Library") here.';
        const output = normalize(roundTrip(input));
        // Link URL and text should survive; title attribute may be dropped
        expect(output).toContain('[OL](https://openlibrary.org');
    });

    /* ---------- lists ---------- */

    test('bullet list survives round-trip', () => {
        const input = '* Item one\n* Item two\n* Item three';
        const output = normalize(roundTrip(input));
        // tiptap-markdown may use different markers (* vs -)
        const lines = output.split('\n').filter(l => l.trim());
        expect(lines).toHaveLength(3);
        lines.forEach(l => expect(l).toMatch(/^[*+-] /));
        expect(output).toContain('Item one');
        expect(output).toContain('Item two');
        expect(output).toContain('Item three');
    });

    test('ordered list survives round-trip', () => {
        const input = '1. First\n2. Second\n3. Third';
        const output = normalize(roundTrip(input));
        expect(output).toContain('First');
        expect(output).toContain('Second');
        expect(output).toContain('Third');
        expect(output).toMatch(/^\d+\. First/m);
    });

    test('nested bullet list indentation is normalized to 4 spaces', () => {
        const input = '* Parent\n    * Child\n        * Grandchild';
        const output = normalize(roundTrip(input));
        // After round-trip through tiptap (2-space) + our post-processing (4-space)
        expect(output).toContain('Parent');
        expect(output).toContain('Child');
        expect(output).toContain('Grandchild');
        // Nested items should have 4-space indentation
        const lines = output.split('\n');
        const childLine = lines.find(l => l.includes('Child') && !l.includes('Grand'));
        if (childLine) {
            expect(childLine).toMatch(/^ {4}[*+-] Child/);
        }
    });

    test('nested ordered list indentation is normalized to 4 spaces', () => {
        const input = '1. Parent\n    1. Child\n        1. Grandchild';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Parent');
        expect(output).toContain('Child');
        expect(output).toContain('Grandchild');
    });

    /* ---------- blockquotes ---------- */

    test('blockquote survives round-trip', () => {
        const input = '> This is a quoted paragraph.';
        const output = normalize(roundTrip(input));
        expect(output).toMatch(/^> /m);
        expect(output).toContain('This is a quoted paragraph.');
    });

    test('multi-line blockquote survives round-trip', () => {
        const input = '> Line one.\n> Line two.';
        const output = normalize(roundTrip(input));
        expect(output).toMatch(/^>/m);
        expect(output).toContain('Line one.');
        expect(output).toContain('Line two.');
    });

    /* ---------- horizontal rule ---------- */

    test('horizontal rule survives round-trip', () => {
        const input = 'Above.\n\n---\n\nBelow.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Above.');
        expect(output).toContain('Below.');
        expect(output).toMatch(/^---$/m);
    });

    /* ---------- images ---------- */

    test('image survives round-trip', () => {
        const input = '![Book cover](https://covers.openlibrary.org/b/id/12345-L.jpg)';
        const output = normalize(roundTrip(input));
        expect(output).toContain('https://covers.openlibrary.org/b/id/12345-L.jpg');
        expect(output).toMatch(/!\[.*\]\(https:\/\/covers\.openlibrary\.org/);
    });

    /* ---------- code (unsupported – should degrade gracefully) ---------- */

    test('inline code degrades to plain text (code disabled)', () => {
        const input = 'Use the `getMarkdown()` function.';
        const output = normalize(roundTrip(input));
        // Code is disabled, so content should still be present even if backticks are lost
        expect(output).toContain('getMarkdown()');
    });

    test('code block degrades to plain text (codeBlock disabled)', () => {
        const input = '```\nconst x = 1;\n```';
        const output = normalize(roundTrip(input));
        // Code blocks are disabled; the text content should survive in some form
        expect(output).toContain('const x = 1;');
    });

    /* ---------- strikethrough (unsupported) ---------- */

    test('strikethrough degrades gracefully (strike disabled)', () => {
        const input = 'This is ~~deleted~~ text.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('deleted');
        expect(output).toContain('text');
    });

    /* ---------- real-world OpenLibrary content ---------- */

    test('LOTR description survives round-trip', () => {
        const input = `Originally published from 1954 through 1956, J.R.R. Tolkien's richly complex series ushered in a new age of epic adventure storytelling. A philologist and illustrator who took inspiration from his work, Tolkien invented the modern heroic quest novel from the ground up, creating not just a world, but a domain, not just a lexicon, but a language, that would spawn countless imitators and lead to the inception of the epic fantasy genre. Today, THE LORD OF THE RINGS is considered "the most influential fantasy novel ever written." (THE ENCYCLOPEDIA OF FANTASY)

During his travels across Middle-earth, the hobbit Bilbo Baggins had found the Ring. But the simple band of gold was far from ordinary; it was in fact the One Ring - the greatest of the ancient Rings of Power. Sauron, the Dark Lord, had infused it with his own evil magic, and when it was lost, he was forced to flee into hiding.

But now Sauron's exile has ended and his power is spreading anew, fueled by the knowledge that his treasure has been found. He has gathered all the Great Rings to him, and will stop at nothing to reclaim the One that will complete his dominion. The only way to stop him is to cast the Ruling Ring deep into the Fire-Mountain at the heart of the land of Mordor--Sauron's dark realm.

Fate has placed the burden in the hands of Frodo Baggins, Bilbo's heir...and he is resolved to bear it to its end. Or his own.`;

        const output = normalize(roundTrip(input));
        // All paragraphs should survive
        expect(output).toContain('J.R.R. Tolkien');
        expect(output).toContain('THE ENCYCLOPEDIA OF FANTASY');
        expect(output).toContain('Middle-earth');
        expect(output).toContain('Frodo Baggins');
        expect(output).toContain('Mordor');
        // Should have multiple paragraphs (separated by blank lines)
        expect(output.split('\n\n').length).toBeGreaterThanOrEqual(4);
    });

    test('Ethan Frome description with bold/italic and many paragraphs survives', () => {
        const input = `*Edith Wharton wrote Ethan Frome as a frame story — meaning that the prologue and epilogue constitute a "frame" around the main story*

**How It All Goes Down**
It's winter. A nameless engineer is in Starkfield, Massachusetts on business and he first sees Ethan Frome at the post office. Ethan is a man in his early fifties who is obviously strong, and obviously crippled.

Ethan has walked from his farm and sawmill into town to pick up Mattie Silver from the church dance. He peeks in the windows of the church basement and sees Mattie dancing with Denis Eady and is jealous.

Ethan liked Mattie from the beginning and worried that Zeena was too hard on her. The two women soon adjusted to each other (sort of) and things weren't as bad as they could have been.`;

        const output = normalize(roundTrip(input));
        // Italic text should survive
        expect(output).toMatch(/\*Edith Wharton/);
        // Bold heading should survive
        expect(output).toMatch(/\*\*How It All Goes Down\*\*/);
        // All paragraphs present
        expect(output).toContain('Starkfield, Massachusetts');
        expect(output).toContain('Mattie Silver');
        expect(output).toContain('Zeena');
    });

    test('content with em-dashes and special punctuation survives', () => {
        const input = 'The author—known for his wit—wrote many books. He said "hello" and \'goodbye\'. Price: $9.99 & tax (10%).';
        const output = normalize(roundTrip(input));
        expect(output).toContain('—');
        expect(output).toContain('"hello"');
        expect(output).toContain('\'goodbye\'');
        expect(output).toContain('$9.99');
        expect(output).toContain('(10%)');
    });

    test('content with multiple links survives', () => {
        const input = 'See [Wikipedia](https://en.wikipedia.org) and [OpenLibrary](https://openlibrary.org) for more.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('[Wikipedia](https://en.wikipedia.org)');
        expect(output).toContain('[OpenLibrary](https://openlibrary.org)');
    });

    /* ---------- mixed content ---------- */

    test('complex mixed content survives round-trip', () => {
        const input = `# Book Title

**Author:** Jane Doe

A great book about *many things*.

## Summary

> "The best book ever written about the subject."

Key points:

* Point one
* Point two
* Point three

Visit [the website](https://example.org) for more.

---

*Published in 2024.*`;

        const output = normalize(roundTrip(input));
        expect(output).toContain('# Book Title');
        expect(output).toContain('**Author:**');
        expect(output).toContain('*many things*');
        expect(output).toContain('## Summary');
        expect(output).toMatch(/^>/m); // blockquote
        expect(output).toContain('Point one');
        expect(output).toContain('Point two');
        expect(output).toContain('[the website](https://example.org)');
        expect(output).toMatch(/^---$/m);
        expect(output).toContain('Published in 2024');
    });

    /* ---------- edge cases ---------- */

    test('empty string round-trips to empty', () => {
        const output = roundTrip('');
        expect(output.trim()).toBe('');
    });

    test('whitespace-only input round-trips to empty', () => {
        const output = roundTrip('   \n\n   ');
        expect(output.trim()).toBe('');
    });

    test('single line with trailing newline', () => {
        const input = 'Hello world.\n';
        const output = normalize(roundTrip(input));
        expect(output).toBe('Hello world.');
    });

    test('content with HTML entities', () => {
        const input = 'Tom & Jerry, 5 > 3, 2 < 4';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Tom');
        expect(output).toContain('Jerry');
    });

    test('parentheses and brackets in text survive', () => {
        const input = 'The author (born 1960) wrote [many books] over the years.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('(born 1960)');
        // Square brackets without link syntax may be tricky
        expect(output).toContain('many books');
    });

    test('very long paragraph survives round-trip', () => {
        const sentence = 'This is a sentence about books and reading. ';
        const input = sentence.repeat(50).trim();
        const output = normalize(roundTrip(input));
        // Should contain the same content
        expect(output.length).toBeGreaterThan(input.length * 0.9);
        expect(output).toContain('books and reading');
    });
});

/* ================================================================== */
/*  List indentation post-processing unit tests                        */
/* ================================================================== */

describe('List indentation post-processing', () => {
    test('converts 2-space indentation to 4-space', () => {
        const input = '* Parent\n  * Child';
        const output = postProcessMarkdown(input);
        expect(output).toBe('* Parent\n    * Child');
    });

    test('converts 4-space (2-level) to 8-space', () => {
        const input = '* A\n  * B\n    * C';
        const output = postProcessMarkdown(input);
        expect(output).toBe('* A\n    * B\n        * C');
    });

    test('handles ordered list markers', () => {
        const input = '1. A\n  1. B\n    1. C';
        const output = postProcessMarkdown(input);
        expect(output).toBe('1. A\n    1. B\n        1. C');
    });

    test('does not modify top-level list items', () => {
        const input = '* A\n* B\n* C';
        const output = postProcessMarkdown(input);
        expect(output).toBe('* A\n* B\n* C');
    });

    test('does not modify non-list content with leading spaces', () => {
        const input = 'Regular paragraph.\n\nAnother paragraph.';
        const output = postProcessMarkdown(input);
        expect(output).toBe(input);
    });

    test('handles + and - list markers', () => {
        const input = '- A\n  - B\n  + C';
        const output = postProcessMarkdown(input);
        expect(output).toBe('- A\n    - B\n    + C');
    });
});

/* ================================================================== */
/*  HTML Block round-trip tests                                        */
/* ================================================================== */

describe('HTML Block round-trip', () => {
    test('raw HTML block is preserved through round-trip', () => {
        const input = '<div class="custom">\n  <p>Hello</p>\n</div>';
        const output = normalize(roundTrip(input));
        expect(output).toContain('<div class="custom">');
        expect(output).toContain('<p>Hello</p>');
        expect(output).toContain('</div>');
    });

    test('HTML table is preserved through round-trip', () => {
        const input = '<table>\n<tr><td>A</td><td>B</td></tr>\n</table>';
        const output = normalize(roundTrip(input));
        expect(output).toContain('<table>');
        expect(output).toContain('<td>A</td>');
        expect(output).toContain('</table>');
    });

    test('mixed markdown and HTML blocks survive', () => {
        const input = '# Title\n\nSome text.\n\n<div class="info">Info box</div>\n\nMore text.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('# Title');
        expect(output).toContain('Some text.');
        expect(output).toContain('Info box');
        expect(output).toContain('More text.');
    });
});

/* ================================================================== */
/*  Mutation detection tests                                           */
/* ================================================================== */

describe('Content mutation detection', () => {
    // These tests verify that specific markdown patterns are NOT silently corrupted

    test('does not add extra blank lines between paragraphs', () => {
        const input = 'Para one.\n\nPara two.\n\nPara three.';
        const output = normalize(roundTrip(input));
        const blankLineCount = (output.match(/\n\n/g) || []).length;
        expect(blankLineCount).toBe(2); // exactly 2 paragraph breaks
    });

    test('does not strip inline formatting from middle of sentence', () => {
        const input = 'Start **middle** end.';
        const output = normalize(roundTrip(input));
        expect(output).toBe('Start **middle** end.');
    });

    test('does not convert heading to paragraph', () => {
        const input = '## Important Section\n\nContent here.';
        const output = normalize(roundTrip(input));
        expect(output).toMatch(/^## Important Section$/m);
    });

    test('does not merge paragraphs into one', () => {
        const input = 'First.\n\nSecond.\n\nThird.';
        const output = normalize(roundTrip(input));
        const paragraphs = output.split('\n\n');
        expect(paragraphs).toHaveLength(3);
    });

    test('does not drop list items', () => {
        const input = '* Apple\n* Banana\n* Cherry\n* Date\n* Elderberry';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Apple');
        expect(output).toContain('Banana');
        expect(output).toContain('Cherry');
        expect(output).toContain('Date');
        expect(output).toContain('Elderberry');
    });

    test('does not drop blockquote markers', () => {
        const input = '> Important quote here.';
        const output = normalize(roundTrip(input));
        expect(output.startsWith('>')).toBe(true);
    });

    test('does not mangle link URLs', () => {
        const input = 'See [docs](https://openlibrary.org/dev/docs?version=2&format=json#section).';
        const output = normalize(roundTrip(input));
        expect(output).toContain('https://openlibrary.org/dev/docs?version=2&format=json#section');
    });

    test('does not mangle image URLs', () => {
        const input = '![cover](https://covers.openlibrary.org/b/id/12345-L.jpg)';
        const output = normalize(roundTrip(input));
        expect(output).toContain('https://covers.openlibrary.org/b/id/12345-L.jpg');
    });
});

/* ================================================================== */
/*  Line break / `breaks: true` behavior tests                         */
/* ================================================================== */

describe('Line break handling (breaks: true)', () => {
    test('single newline within paragraph creates a hard break', () => {
        // With breaks:true, a single newline is treated as <br>, not a continuation
        const input = 'Line one\nLine two';
        const output = normalize(roundTrip(input));
        // Both lines should be present
        expect(output).toContain('Line one');
        expect(output).toContain('Line two');
    });

    test('\\r\\n line endings are handled', () => {
        const input = 'Line one\r\nLine two\r\n\r\nParagraph two.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Line one');
        expect(output).toContain('Line two');
        expect(output).toContain('Paragraph two.');
    });

    test('trailing spaces before newline do not cause issues', () => {
        const input = 'Line one   \nLine two';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Line one');
        expect(output).toContain('Line two');
    });

    test('multiple consecutive blank lines collapse to paragraph break', () => {
        const input = 'Para one.\n\n\n\nPara two.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Para one.');
        expect(output).toContain('Para two.');
        // Should be exactly one paragraph break
        expect(output.split('\n\n').length).toBe(2);
    });
});

/* ================================================================== */
/*  Idempotency tests – multiple round-trips should converge           */
/* ================================================================== */

describe('Idempotency (double round-trip)', () => {
    function doubleRoundTrip(input) {
        const first = roundTrip(input);
        const second = roundTrip(first);
        return { first: normalize(first), second: normalize(second) };
    }

    test('plain text is idempotent after first round-trip', () => {
        const { first, second } = doubleRoundTrip('Hello world.');
        expect(second).toBe(first);
    });

    test('formatted text is idempotent after first round-trip', () => {
        const { first, second } = doubleRoundTrip('This is **bold** and *italic*.');
        expect(second).toBe(first);
    });

    test('complex content is idempotent after first round-trip', () => {
        const input = `# Title

**Author:** Someone

> A great quote.

* List item one
* List item two

Visit [here](https://example.org).`;

        const { first, second } = doubleRoundTrip(input);
        expect(second).toBe(first);
    });

    test('nested lists are idempotent after first round-trip', () => {
        const input = '* A\n    * B\n        * C';
        const { first, second } = doubleRoundTrip(input);
        expect(second).toBe(first);
    });

    test('real-world LOTR content is idempotent after first round-trip', () => {
        const input = `Originally published from 1954 through 1956, J.R.R. Tolkien's richly complex series ushered in a new age of epic adventure storytelling.

During his travels across Middle-earth, the hobbit Bilbo Baggins had found the Ring. But the simple band of gold was far from ordinary; it was in fact the One Ring.

Fate has placed the burden in the hands of Frodo Baggins, Bilbo's heir...and he is resolved to bear it to its end. Or his own.`;

        const { first, second } = doubleRoundTrip(input);
        expect(second).toBe(first);
    });

    test('content with links is idempotent after first round-trip', () => {
        const { first, second } = doubleRoundTrip(
            'See [Wikipedia](https://en.wikipedia.org/wiki/Main_Page) and [OL](https://openlibrary.org).'
        );
        expect(second).toBe(first);
    });
});

/* ================================================================== */
/*  Unsupported syntax degradation — document what gets lost            */
/* ================================================================== */

describe('Unsupported syntax degradation', () => {
    test('markdown table degrades but content survives', () => {
        const input = '| Col A | Col B |\n|-------|-------|\n| 1     | 2     |';
        const output = normalize(roundTrip(input));
        // Tables are not supported by the editor, content should still be present
        expect(output).toContain('Col A');
        expect(output).toContain('Col B');
    });

    test('reference-style links degrade but URL text survives', () => {
        const input = 'See [the docs][1].\n\n[1]: https://openlibrary.org';
        const output = normalize(roundTrip(input));
        expect(output).toContain('the docs');
    });

    test('heading levels 5-6 degrade to paragraph text', () => {
        const input = '##### Deep Heading\n\nContent.';
        const output = normalize(roundTrip(input));
        expect(output).not.toMatch(/^#####/m);
        expect(output).toContain('Deep Heading');
        expect(output).toContain('Content.');
    });
});

/* ================================================================== */
/*  Real OL page content tests                                         */
/*  Patterns discovered from live testing against openlibrary.org      */
/* ================================================================== */

describe('Real OL page patterns', () => {

    // /volunteer page uses reference-style links extensively
    test('reference-style links: text survives, URLs are resolved inline', () => {
        const input = `Open Library is a [open source][1] project.

If you want to help, [volunteer][2]!

  [1]: https://github.com/internetarchive/openlibrary
  [2]: https://openlibrary.org/volunteer`;

        const output = normalize(roundTrip(input));
        // Reference links get inlined — this is expected and safe
        expect(output).toContain('open source');
        expect(output).toContain('https://github.com/internetarchive/openlibrary');
        expect(output).toContain('volunteer');
        // Reference definitions should be gone (inlined)
        expect(output).not.toMatch(/^\s*\[\d+\]:/m);
        // Should be idempotent after conversion
        const second = normalize(roundTrip(output));
        expect(second).toBe(output);
    });

    // /volunteer page has <a name="..."> anchors inside headings.
    // These are legacy navigation anchors — the name attribute is lost
    // but heading text and links survive. The volunteer page should be
    // updated to use heading IDs instead.
    test('<a name="x"> anchors in headings: name lost, text and links survive', () => {
        const input = '### <a name="librarian"> [Librarian](https://openlibrary.org/librarians)</a>';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Librarian');
        expect(output).toContain('https://openlibrary.org/librarians');
        // name attribute is not preserved — known/accepted
        expect(output).not.toContain('name=');
        // Should be idempotent after initial conversion
        const second = normalize(roundTrip(output));
        expect(second).toBe(output);
    });

    // /about/lib uses h3 headings — now supported
    test('h3 headings from /about/lib page survive round-trip', () => {
        const input = `### futurelib

We're building a new schema.

### OLNs

Open Library Numbers are unique identifiers.

### Some useful data

Here is some data.`;

        const output = normalize(roundTrip(input));
        expect(output).toContain('### futurelib');
        expect(output).toContain('### OLNs');
        expect(output).toContain('### Some useful data');
        expect(output).toContain('building a new schema');
        expect(output).toBe(normalize(input));
    });

    // /about/lib uses _underscores_ for italic
    test('underscore italic from /about/lib is preserved as emphasis', () => {
        const input = 'We\'re currently calling this new schema _futurelib_ and we hope to hold meetings.';
        const output = normalize(roundTrip(input));
        // May convert _ to * — both are valid emphasis
        expect(output).toMatch(/(\*|_)futurelib(\*|_)/);
        expect(output).toContain('calling this new schema');
    });

    // /help/faq/editing has <a href="#top">Top</a> inline HTML anchors
    test('inline HTML anchor tags from FAQ page', () => {
        const input = 'Return to <a href="#top">Top</a> of page.';
        const output = normalize(roundTrip(input));
        // Inline HTML may be preserved or converted to markdown link
        expect(output).toContain('Top');
        // Should be idempotent
        const second = normalize(roundTrip(output));
        expect(second).toBe(output);
    });

    // /help/faq/editing uses leading-space list items
    test('leading-space list items from FAQ page normalize correctly', () => {
        const input = ' - Hardcovers\n - Trade Paperbacks\n - Mass Market Paperbacks\n - Spiral-Bound';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Hardcovers');
        expect(output).toContain('Trade Paperbacks');
        expect(output).toContain('Mass Market Paperbacks');
        expect(output).toContain('Spiral-Bound');
        // Should be idempotent
        const second = normalize(roundTrip(output));
        expect(second).toBe(output);
    });

    // /volunteer has mailto: links with query params
    test('mailto links with encoded params survive', () => {
        const input = '[Contribute as a Librarian!](mailto:lisas@archive.org?subject=Open%20Library)';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Contribute as a Librarian!');
        expect(output).toContain('mailto:');
        // Should be idempotent
        const second = normalize(roundTrip(output));
        expect(second).toBe(output);
    });

    // Ethan Frome from API: description with \r\n, bold, italic, many paragraphs
    test('Ethan Frome with \\r\\n line endings (as stored in API)', () => {
        const input = '*Edith Wharton wrote Ethan Frome*\r\n\r\n**How It All Goes Down**\r\nIt\'s winter. A nameless engineer is in Starkfield.\r\n\r\nEthan has walked from his farm into town.';
        const output = normalize(roundTrip(input));
        expect(output).toContain('Edith Wharton');
        expect(output).toContain('How It All Goes Down');
        expect(output).toContain('Starkfield');
        expect(output).toContain('farm into town');
        // Should be idempotent
        const second = normalize(roundTrip(output));
        expect(second).toBe(output);
    });

    // Large volunteer page excerpt with mixed content
    test('volunteer page excerpt with mixed markdown features', () => {
        const input = `## Welcome!

Open Library is a non-profit, [open source](https://github.com/internetarchive/openlibrary), digital public library.

## How it Works

Open Library hosts an invite-only community chat room on slack.

## Choose Your Character

Want to get involved? First, lets choose your character:

**Librarian**

Open Library's book catalog has millions of books and thousands of data errors.

* [Contribute as a Frontend Engineer!](mailto:test@example.org) (javascript, vue, css/less)
* [Contribute as a Backend Engineer!](mailto:test@example.org) (python, web.py)
* [Contribute as a Data Engineer!](mailto:test@example.org) (imports, bots)

**Designer & User Researcher**

Does OpenLibrary.org look like it's from the the 90's? Help us fix that!`;

        const output = normalize(roundTrip(input));
        // All structural elements should survive
        expect(output).toContain('## Welcome!');
        expect(output).toContain('## How it Works');
        expect(output).toContain('## Choose Your Character');
        expect(output).toContain('open source');
        expect(output).toContain('**Librarian**');
        expect(output).toContain('Frontend Engineer');
        expect(output).toContain('Backend Engineer');
        expect(output).toContain('Data Engineer');
        expect(output).toContain('**Designer & User Researcher**');
        // Should be idempotent
        const second = normalize(roundTrip(output));
        expect(second).toBe(output);
    });
});

/* ================================================================== */
/*  Code support (enableCode / enable-code attribute)                  */
/* ================================================================== */

describe('OLMarkdownEditor code support', () => {

    /* ---------- default: code disabled ---------- */

    test('without enableCode, fenced code block is flattened to paragraphs', () => {
        const input = '```\nblock code here\n```';
        const output = normalize(roundTrip(input));
        // When code support is off, fences should not survive
        expect(output).not.toContain('```');
    });

    test('without enableCode, backtick inline code is flattened', () => {
        const input = 'Some `inline code` here.';
        const output = normalize(roundTrip(input));
        expect(output).not.toContain('`inline code`');
    });

    /* ---------- enableCode: inline code ---------- */

    test('inline code survives round-trip when enableCode is true', () => {
        const input = 'Then some `inline code` here.';
        const output = normalize(roundTrip(input, { enableCode: true }));
        expect(output).toContain('`inline code`');
        const second = normalize(roundTrip(output, { enableCode: true }));
        expect(second).toBe(output);
    });

    test('inline code with special characters survives', () => {
        const input = 'Use `foo.bar(x, y)` to call it.';
        const output = normalize(roundTrip(input, { enableCode: true }));
        expect(output).toContain('`foo.bar(x, y)`');
    });

    /* ---------- enableCode: fenced code block ---------- */

    test('fenced code block survives round-trip when enableCode is true', () => {
        const input = '```\nblock code here\n```';
        const output = normalize(roundTrip(input, { enableCode: true }));
        // Must keep triple backticks and the contents on their own line
        expect(output).toMatch(/```\s*\n?block code here\n?```/);
        // Must NOT contain <br /> injected into the code block
        expect(output).not.toContain('<br');
        // Must NOT collapse to a single-line `...` form
        expect(output).not.toMatch(/^`[^`\n]*block code here[^`\n]*`$/m);
        // Idempotent
        const second = normalize(roundTrip(output, { enableCode: true }));
        expect(second).toBe(output);
    });

    test('fenced code block with language tag survives', () => {
        const input = '```js\nconst x = 1;\nconsole.log(x);\n```';
        const output = normalize(roundTrip(input, { enableCode: true }));
        expect(output).toContain('```');
        expect(output).toContain('const x = 1;');
        expect(output).toContain('console.log(x);');
        expect(output).not.toContain('<br');
    });

    test('multi-line code block preserves newlines (not <br />)', () => {
        const input = '```\nline one\nline two\nline three\n```';
        const output = normalize(roundTrip(input, { enableCode: true }));
        // All three lines must be on their own lines
        expect(output).toMatch(/line one\nline two\nline three/);
        expect(output).not.toContain('<br');
    });

    /* ---------- combined: user's reproduction case ---------- */

    test('heading + code block + inline code + html block (user repro)', () => {
        const input = [
            '## Will it work',
            '',
            '```',
            'block code here',
            '```',
            '',
            'Then some `inline code` here.',
            '',
            '<div>and finally an html block here</div>'
        ].join('\n');
        const output = normalize(roundTrip(input, { enableCode: true }));

        expect(output).toContain('## Will it work');
        expect(output).toMatch(/```\s*\n?block code here\n?```/);
        expect(output).toContain('`inline code`');
        expect(output).toContain('<div>and finally an html block here</div>');
        // The bug-shape from the screenshot: single backticks with <br /> inside.
        expect(output).not.toContain('<br');
        expect(output).not.toMatch(/`[^`\n]*<br[^`]*`/);

        const second = normalize(roundTrip(output, { enableCode: true }));
        expect(second).toBe(output);
    });

    /* ---------- edge cases ---------- */

    test('code block containing markdown-like characters is preserved verbatim', () => {
        const input = '```\n**not bold** and *not italic*\n# not a heading\n```';
        const output = normalize(roundTrip(input, { enableCode: true }));
        expect(output).toContain('**not bold**');
        expect(output).toContain('*not italic*');
        expect(output).toContain('# not a heading');
    });

    test('inline code next to bold/italic does not bleed', () => {
        const input = '**bold** and `code` and *italic*.';
        const output = normalize(roundTrip(input, { enableCode: true }));
        expect(output).toContain('**bold**');
        expect(output).toContain('`code`');
        expect(output).toContain('*italic*');
    });
});
