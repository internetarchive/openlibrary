// used in templates/lists/preview.html
export function sprintf(s) {
    var args = arguments;
    var i = 1;
    return s.replace(/%[%s]/g, function(match) {
        if (match == "%%")
            return "%";
        else
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
    return n == 1? s1 : s2;
}
