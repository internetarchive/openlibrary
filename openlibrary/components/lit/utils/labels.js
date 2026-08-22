/**
 * Label resolution shared by the components that render translated strings.
 *
 * Each component owns a `DEFAULT_LABELS` map of English defaults and takes a
 * `labels` object that overrides it. A composing parent passes its whole
 * `labels` blob straight down — extra keys a child doesn't know are harmless,
 * so one server-rendered blob can feed a whole subtree.
 */

/** "%(name)s" style interpolation, matching the server-side i18n strings. */
export function fmt(template, vars) {
    return template.replace(/%\((\w+)\)s/g, (_, k) => (vars[k] ?? ''));
}

/**
 * Resolve one label: the instance override wins, then the component's own
 * default, then the key itself — a missing string shows up as its key rather
 * than as blank space.
 */
export function translate(labels, defaults, key, vars) {
    const s = labels?.[key] ?? defaults?.[key] ?? key;
    return vars ? fmt(s, vars) : s;
}
