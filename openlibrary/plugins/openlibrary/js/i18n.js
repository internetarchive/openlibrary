// used in templates/lists/preview.html
export function sprintf(s) {
    const args = arguments;
    let i = 1;
    return s.replace(/%./g, function(match) {
        if (match === '%%')
            return '%';
        // See https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting
        else if ('diouxXeEfFgGcrsa'.indexOf(match[1]) !== -1)
            return args[i++];
        else
            throw new Error(`unsupported format character '${match[1]}'`);
    });
}

// dummy i18n functions

// used in plugins/upstream/code.py
export function ugettext(s) {  // eslint-disable-line no-unused-vars
    return sprintf.apply(null, arguments);
}

// used in templates/borrow/read.html
export function ungettext(s1, s2, n) {
    return n === 1? s1 : s2;
}
