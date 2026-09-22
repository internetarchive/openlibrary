/**
 * Entry point for the librarian workbench bundle (ol-workbench.js).
 *
 * The workbench is a librarian-only tool, so it is built as its own bundle
 * and loaded only by the templates that use it (templates/librarians/*),
 * not by the site-wide ol-components.js.
 *
 * It imports the site entry first so that the primitives it composes
 * (ol-button, ol-dialog, ol-icon, …) stay inside ol-components.js instead of
 * being hoisted into a shared chunk that every page would have to fetch.
 * Both bundles come out of one Vite build, so each module (and its define())
 * still evaluates once per page.
 */

import '../index.js';

export { OlBatchPreview } from './OlBatchPreview.js';
export { OlWorkbenchGrid } from './OlWorkbenchGrid.js';
export { OlRecordPanel } from './OlRecordPanel.js';
export { OlWorkbenchActionForm } from './OlWorkbenchActionForm.js';
export { OlWorkbench } from './OlWorkbench.js';
