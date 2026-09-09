/*
 * Explicit jquery-ui bootstrap for the `dialog` widget.
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
import 'jquery-ui/ui/keycode';
import 'jquery-ui/ui/position';
import 'jquery-ui/ui/unique-id';
import 'jquery-ui/ui/data';
import 'jquery-ui/ui/plugin';
import 'jquery-ui/ui/scroll-parent';
import 'jquery-ui/ui/focusable';
import 'jquery-ui/ui/tabbable';
import 'jquery-ui/ui/widgets/mouse';
import 'jquery-ui/ui/widgets/controlgroup';
import 'jquery-ui/ui/form-reset-mixin';
import 'jquery-ui/ui/labels';
import 'jquery-ui/ui/widgets/checkboxradio';
import 'jquery-ui/ui/widgets/button';
import 'jquery-ui/ui/disable-selection';
import 'jquery-ui/ui/widgets/draggable';
import 'jquery-ui/ui/widgets/resizable';
import 'jquery-ui/ui/widgets/dialog';
