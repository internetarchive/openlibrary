/**
 * Config for @custom-elements-manifest/analyzer.
 *
 * Scans the Lit web components in openlibrary/components/lit/ and emits a
 * Custom Elements Manifest (custom-elements.json) describing each component's
 * public API: properties, attributes, events, slots, CSS custom properties and
 * CSS parts — sourced from the JSDoc on the components.
 *
 * The manifest is generated, not committed (see .gitignore), and read at runtime
 * by the /developers/design page to render API reference tables. Regenerate with
 * `npm run build-assets:lit-manifest` (also run as part of `make lit-components`).
 */
export default {
    globs: ['openlibrary/components/lit/**/*.js'],
    // index.js is pure re-exports; icons.generated.js is a bag of svg templates;
    // editor-core/html-block are internal helpers for the markdown editor.
    // None of them define a public custom element.
    exclude: [
        'openlibrary/components/lit/index.js',
        'openlibrary/components/lit/icons.generated.js',
        'openlibrary/components/lit/editor-core.js',
        'openlibrary/components/lit/html-block.js',
    ],
    outdir: 'openlibrary/components/lit',
    litelement: true,
};
