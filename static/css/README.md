# CSS Architecture

All files in this folder with the `page-` prefix are **entry points** — each one corresponds to a page type and is compiled by webpack into a standalone CSS bundle.

## Entry points

Entry point files (e.g., `page-home.css`, `page-book.css`) use `@import` to pull in component styles from the `components/`, `base/`, and `layout/` subdirectories.

## Render-blocking CSS

Entry points prefixed with `page-` are loaded in the `<head>` of the document and are render-blocking. Be mindful of file size when adding imports to these files.

## Components

Groups of styles make up a "component" — a self-contained feature of a page.

If you are building a new component, create a CSS file inside the `components/` folder and reference it via `@import` from the appropriate `page-*.css` entry point(s).

## Design tokens

Shared values (colors, spacing, font sizes, breakpoints) are defined as CSS custom properties in `tokens.css`, which is loaded globally in the `<head>`.

## Build

CSS is compiled via webpack (`webpack.config.css.js`). Run:

    make css

To watch for changes during development:

    npm run watch:css
