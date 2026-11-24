/*
 * Explicit jquery-ui bootstrap for the `sortable` widget (plus the
 * `disable-selection` behavior it pairs with). Used by covers.js for
 * drag-to-reorder; sortable's own deps (mouse/data/scroll-parent) are listed
 * in topological order (deps before dependents).
 *
 * jquery-ui 1.14 ships UMD only, and its inter-module deps are AMD
 * (`define(["jquery","../widget",…], factory)`). Vite/Rolldown has no AMD
 * loader, so importing a widget alone would run the UMD's browser-globals
 * branch (`factory(jQuery)`) without its deps — `$.widget` would be undefined.
 * This module replaces the old `jqueryUiAmdDeps` transform plugin: the deps
 * are listed here in topological order (deps before dependents) instead of
 * being regex-extracted from jquery-ui's source at build time.
 *
 * Keep this list in sync with the AMD `define([...])` header of each file in
 * node_modules/jquery-ui when upgrading the pinned 1.14.2 version.
 */
import 'jquery-ui/ui/version';
import 'jquery-ui/ui/widget';
import 'jquery-ui/ui/widgets/mouse';
import 'jquery-ui/ui/data';
import 'jquery-ui/ui/scroll-parent';
import 'jquery-ui/ui/disable-selection';
import 'jquery-ui/ui/widgets/sortable';
