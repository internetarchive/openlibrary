/**
 * Thin ESM entry for the `all` bundle.
 *
 * The real app (index.js) is imported dynamically so it becomes a *chunk*
 * rather than the entry. If index.js were the entry, rolldown would hoist
 * modules shared with lazy chunks (utils.js, …) into the entry, and those lazy
 * chunks would then `import … from "./all.js"`. Because the entry is also
 * served via `<script src="all.js?v=…">`, that re-import has a *different URL*
 * and the browser treats it as a second module instance — re-running the entry's
 * side effects (e.g. `customElements.define()` → "ol-search-modal has already
 * been used"). Keeping the entry side-effect-free avoids that entirely.
 *
 * See vite-js.config.mjs.
 */
import('./index.js');
