/**
 * Translated strings for UI the browser renders: Lit and Vue components and
 * page scripts.
 *
 * Code calls `_()` (or `ngettext()`) with the English string. Extraction puts
 * those calls in messages.pot like the server's, and the page head loads this
 * language's translations of them (`window.OL_I18N`, from static/build/i18n/<lang>.js,
 * which `make i18n` writes); see docs/i18n/i18n.md. Without a translation, the English shows.
 *
 * Older components get their strings from the page template instead, as a JSON
 * attribute: each owns a map of English defaults (`DEFAULT_LABELS` in the Lit
 * components) and takes a `labels` object that overrides it. A composing parent passes its whole
 * `labels` blob straight down — extra keys a child doesn't know are harmless,
 * so one server-rendered blob can feed a whole subtree.
 *
 * A label can be a function of the count (`count => ngettext(...)`), which
 * `translate` calls with `vars.count`, or a plural set: an object keyed by CLDR plural category
 * (`one`, `other`, and for languages that need them `zero`, `two`, `few`,
 * `many`). `translate` picks the form for `vars.count` with the page
 * language's rules, so a translation blob can carry every form its language
 * has rather than a singular/plural pair that only fits English.
 *
 * jsdef templates get their own `_()` and `ungettext()` in the browser, from
 * jsdef.js; those are pass-throughs, not translations.
 */

/** "%(name)s" (or "%(name)d") style interpolation, matching the server-side i18n strings. */
export function fmt(template, vars) {
    return template.replace(/%\((\w+)\)[sd]/g, (_, k) => vars[k] ?? '');
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

function translations() {
    return window.OL_I18N ?? {};
}

/** `msgid` in the page language, or `msgid` itself (the English) when it has no translation. */
export function gettext(msgid) {
    const text = translations()[msgid];
    return typeof text === 'string' ? text : msgid;
}
export { gettext as _ };

/** The form of a plural string for `count`, in the page language when it has a translation. */
export function ngettext(singular, pluralForm, count) {
    const forms = translations()[singular];
    if (forms && typeof forms === 'object') return plural(forms, count);
    return Number(count) === 1 ? singular : pluralForm;
}

/**
 * Resolve one label: the instance override wins, then the component's own
 * default, then the key itself — a missing string shows up as its key rather
 * than as blank space.
 */
export function translate(labels, defaults, key, vars) {
    let s = labels?.[key] ?? defaults?.[key] ?? key;
    if (typeof s === 'function') s = s(vars?.count ?? 0);
    else if (typeof s === 'object') s = plural(s, vars?.count ?? 0);
    return vars ? fmt(s, vars) : s;
}

/**
 * Fill `%s` placeholders in order, or `%(name)s` ones from an object passed as
 * the only argument; `%%` is a literal percent. jsdef templates and the search
 * modal use it. New code uses `translate`, which also picks plural forms.
 */
export function sprintf(s) {
    const args = arguments;
    let i = 1;
    return s.replace(/%(?:\((\w+)\))?[%s]/g, function (match, name) {
        if (match === '%%') return '%';
        if (name) return args[1][name];
        return args[i++];
    });
}
