/**
 * How many options a picker holds before it earns a filter input.
 *
 * Shown when the count *exceeds* this — under it the options are scannable and
 * the field is chrome, and on mobile it is chrome that pushes them down a tray.
 * Shared so the pickers agree with each other: a reader who has learnt where
 * the filter appears in one popover has learnt it for the rest.
 */
export const FILTER_THRESHOLD = 8;
