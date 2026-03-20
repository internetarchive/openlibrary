/**
 * Long-running SSR server for Lit web components.
 *
 * Communicates over stdin/stdout using a simple line-delimited JSON protocol.
 * The Python DSD helper (openlibrary/core/dsd.py) starts this process once
 * and sends render requests to it, avoiding the ~65ms Node.js startup cost
 * on every render.
 *
 * Protocol:
 *   → (stdin)  One JSON object per line: { "tag": "ol-read-more", "attrs": {...}, "content": "..." }
 *   ← (stdout) One JSON object per line: { "html": "..." } or { "error": "..." }
 *
 * The process exits cleanly when stdin is closed (Python process ends).
 */

import { render } from '@lit-labs/ssr';
import { html } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { collectResultSync } from '@lit-labs/ssr/lib/render-result.js';
import { createInterface } from 'readline';

// Import components — registers them via customElements.define()
import '../OLReadMore.js';
import '../OlPagination.js';

/**
 * Render an HTML string containing Lit custom elements to DSD HTML.
 */
function ssrRender(templateStr) {
    const result = render(html`${unsafeHTML(templateStr)}`);
    return collectResultSync(result);
}

// Signal to Python that we're ready to accept requests
process.stdout.write(JSON.stringify({ ready: true }) + '\n');

// Read line-delimited JSON requests from stdin
const rl = createInterface({ input: process.stdin });

rl.on('line', (line) => {
    try {
        const req = JSON.parse(line);
        const { tag, attrs = {}, content = '' } = req;

        // Build the HTML template from the request
        const attrStr = Object.entries(attrs)
            .map(([k, v]) => `${k}="${String(v).replace(/"/g, '&quot;')}"`)
            .join(' ');
        const templateStr = content
            ? `<${tag} ${attrStr}>${content}</${tag}>`
            : `<${tag} ${attrStr}></${tag}>`;

        const rendered = ssrRender(templateStr);
        process.stdout.write(JSON.stringify({ html: rendered }) + '\n');
    } catch (err) {
        process.stdout.write(
            JSON.stringify({ error: err.message }) + '\n'
        );
    }
});

rl.on('close', () => {
    process.exit(0);
});
