/* eslint-disable no-unused-vars */
// used in templates/lists/preview.html
function sprintf(s) {
    var args = arguments;
    var i = 1;
    return s.replace(/%[%s]/g, function(match) {
        if (match == "%%")
            return "%";
        else
            return args[i++];
    });
}
/* eslint-enable no-unused-vars */

// dummy i18n functions

/* eslint-disable no-unused-vars */
// used in plugins/upstream/code.py
function ugettext(s) {
    return s;
}
var _ = ugettext;
/* eslint-enable no-unused-vars */

/* eslint-disable no-unused-vars */
// used in templates/borrow/read.html
function ungettext(s1, s2, n) {
    return n == 1? s1 : s2;
}
/* eslint-enable no-unused-vars */
