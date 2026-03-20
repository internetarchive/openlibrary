/**
 * Entry point for Lit web components
 *
 * This file exports all Lit-based web components for the Open Library project.
 * Components are bundled together via Vite for production use.
 *
 * IMPORTANT: The hydration support module MUST be imported before any Lit
 * component modules. It enables Lit to detect and hydrate server-rendered
 * Declarative Shadow DOM instead of re-rendering from scratch.
 */

// Enable hydration of server-rendered Declarative Shadow DOM.
// Must come before any component imports.
import '@lit-labs/ssr-client/lit-element-hydrate-support.js';

// Export components (importing also registers them as custom elements)
export { OLReadMore } from './OLReadMore.js';
export { OlPagination } from './OlPagination.js';

