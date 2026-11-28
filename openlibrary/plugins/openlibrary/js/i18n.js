/**
 * Translated strings for UI the browser renders: Lit and Vue components and
 * page scripts.
 *
 * Code calls `_()` (or `ngettext()`) with the English string. Extraction puts
 * those calls in messages.pot like the server's, and the page head loads this
 * language's translations of them (`window.OL_I18N`, from static/build/i18n/<lang>.js,
 * which `make i18n` writes); see docs/i18n/i18n.md. Without a translation, the English shows.
 *
 * Plurals come from the same file: `window.OL_I18N_PLURALS` maps a plural's
 * singular to its forms in the language's .po order, and
 * `window.OL_I18N_PLURAL_RULE` is the .po's Plural-Forms rule, which turns a
 * count into an index into those forms. So `ngettext` picks exactly the form
 * the server would, for every form the language has, not just a
 * singular/plural pair that only fits English.
 *
 * jsdef templates get their own `_()` and `ungettext()` in the browser, from
 * jsdef.js; those are pass-throughs, not translations.
 */

/** "%(name)s" (or "%(name)d") style interpolation, matching the server-side i18n strings. */
export function fmt(template, vars) {
    return template.replace(/%\((\w+)\)[sd]/g, (_, k) => vars[k] ?? '');
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
    const n = Number(count);
    const forms = window.OL_I18N_PLURALS?.[singular];
    const form = Array.isArray(forms) && window.OL_I18N_PLURAL_RULE ? forms[window.OL_I18N_PLURAL_RULE(n)] : undefined;
    return form ?? (n === 1 ? singular : pluralForm);
}

/**
 * One string from a component's table of `_()` strings, with its `%(name)s`
 * placeholders filled from `vars`. An entry can be a function of the count
 * (`count => ngettext(...)`), called with `vars.count`. A missing key shows up
 * as the key itself rather than as blank space.
 */
export function lookup(strings, key, vars) {
    let s = strings[key] ?? key;
    if (typeof s === 'function') s = s(vars?.count ?? 0);
    return vars ? fmt(s, vars) : s;
}

/**
 * Fill `%s` placeholders in order, or `%(name)s` ones from an object passed as
 * the only argument; `%%` is a literal percent. jsdef templates use it. New code
 * uses `fmt` with `_()` / `ngettext()` instead.
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
