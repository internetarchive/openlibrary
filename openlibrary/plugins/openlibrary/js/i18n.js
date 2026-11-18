// used in templates/lists/preview.html
// Fills %s in order, or %(name)s from an object passed as the only argument.
export function sprintf(s) {
    var args = arguments;
    var i = 1;
    return s.replace(/%(?:\((\w+)\))?[%s]/g, function (match, name) {
        if (match === '%%') return '%';
        if (name) return args[1][name];
        return args[i++];
    });
}

// dummy i18n functions

// used in plugins/upstream/code.py
export function ugettext(s) {
    return s;
}

// used in templates/borrow/read.html
export function ungettext(s1, s2, n) {
    return n === 1 ? s1 : s2;
}
