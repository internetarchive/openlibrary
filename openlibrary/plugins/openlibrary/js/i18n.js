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

// dummy i18n functions

function ugettext(s) {
    return s;
}
var _ = ugettext;

function ungettext(s1, s2, n) {
    return n == 1? s1 : s2;
}