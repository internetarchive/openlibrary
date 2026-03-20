/**
 * Node.js SSR renderer for Lit web components.
 *
 * Uses the official @lit-labs/ssr package to render components using their
 * real render() methods — no manual HTML replication needed.
 *
 * Called by the Python DSD helpers (openlibrary/core/dsd.py) via subprocess.
 *
 * Usage (single template via CLI argument):
 *   node openlibrary/components/lit/ssr/render.mjs '<ol-read-more max-height="80px">content</ol-read-more>'
 *
 * Usage (batch via stdin — JSON array of HTML strings):
 *   echo '["<ol-read-more>text</ol-read-more>","<ol-pagination total-pages=\"5\" current-page=\"1\"></ol-pagination>"]' | \
 *     node openlibrary/components/lit/ssr/render.mjs --batch
 *
 * Usage (single structured request via stdin):
 *   echo '{"tag":"ol-read-more","attrs":{"max-height":"80px"},"content":"<p>text</p>"}' | \
 *     node openlibrary/components/lit/ssr/render.mjs
 *
 * Output: Rendered HTML with Declarative Shadow DOM and Lit template markers
 * for proper client-side hydration.
 */

import { render } from '@lit-labs/ssr';
import { html } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { collectResultSync } from '@lit-labs/ssr/lib/render-result.js';

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

/**
 * Build an HTML string from a structured request object and render it.
 *
 * @param {Object} request - { tag, attrs, content }
 */
function renderFromRequest(request) {
    const { tag, attrs = {}, content = '' } = request;
    const attrStr = Object.entries(attrs)
        .map(([k, v]) => `${k}="${String(v).replace(/"/g, '&quot;')}"`)
        .join(' ');
    const templateStr = content
        ? `<${tag} ${attrStr}>${content}</${tag}>`
        : `<${tag} ${attrStr}></${tag}>`;
    return ssrRender(templateStr);
}

/**
 * Read all of stdin as a string.
 */
async function readStdin() {
    let input = '';
    process.stdin.setEncoding('utf-8');
    for await (const chunk of process.stdin) {
        input += chunk;
    }
    return input;
}

// --- Main ---
const args = process.argv.slice(2);

if (args.includes('--batch')) {
    // Batch mode: JSON array from stdin
    const input = await readStdin();
    const requests = JSON.parse(input);
    const results = requests.map((req) =>
        typeof req === 'string' ? ssrRender(req) : renderFromRequest(req)
    );
    process.stdout.write(JSON.stringify(results));
} else if (args.length > 0 && !args[0].startsWith('-')) {
    // Single template from CLI argument
    process.stdout.write(ssrRender(args[0]));
} else {
    // Single request from stdin (JSON string or object)
    const input = await readStdin();
    const req = JSON.parse(input);
    const rendered =
        typeof req === 'string' ? ssrRender(req) : renderFromRequest(req);
    process.stdout.write(rendered);
}
