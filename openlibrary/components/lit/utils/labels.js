/**
 * Label resolution shared by the components that render translated strings.
 *
 * Each component owns a `DEFAULT_LABELS` map of English defaults and takes a
 * `labels` object that overrides it. A composing parent passes its whole
 * `labels` blob straight down — extra keys a child doesn't know are harmless,
 * so one server-rendered blob can feed a whole subtree.
 *
 * A label can also be a plural set: an object keyed by CLDR plural category
 * (`one`, `other`, and for languages that need them `zero`, `two`, `few`,
 * `many`). `translate` picks the form for `vars.count` with the page
 * language's rules, so a translation blob can carry every form its language
 * has rather than a singular/plural pair that only fits English.
 */

/** "%(name)s" style interpolation, matching the server-side i18n strings. */
export function fmt(template, vars) {
    return template.replace(/%\((\w+)\)s/g, (_, k) => (vars[k] ?? ''));
}

let _rules = null;
function pluralCategory(count) {
    const lang = document.documentElement.lang || 'en';
    if (!_rules || _rules.lang !== lang) {
        // A lang the runtime doesn't know falls back to English rules rather
        // than throwing, which is what it does for `en` too.
        let rules;
        try {
            rules = new Intl.PluralRules(lang);
        } catch {
            rules = new Intl.PluralRules('en');
        }
        _rules = { lang, rules };
    }
    return _rules.rules.select(count);
}

/** Pick the form of a plural set for `count`; `other` is the required fallback. */
export function plural(forms, count) {
    return forms[pluralCategory(Number(count))] ?? forms.other;
}

/**
 * Resolve one label: the instance override wins, then the component's own
 * default, then the key itself — a missing string shows up as its key rather
 * than as blank space.
 */
export function translate(labels, defaults, key, vars) {
    let s = labels?.[key] ?? defaults?.[key] ?? key;
    if (typeof s === 'object') s = plural(s, vars?.count ?? 0);
    return vars ? fmt(s, vars) : s;
}
