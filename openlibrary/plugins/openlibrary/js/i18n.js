// used in templates/lists/preview.html
export function sprintf(s) {
    var args = arguments;
    var i = 1;
    return s.replace(/%[%s]/g, function(match) {
        if (match === '%%')
            return '%';
        else
            return args[i++];
    });
}

// dummy i18n functions

const PYTHON_TEMPLATE_ARG_RE = /(?<=%)%([sd])/g;
const PYTHON_TEMPLATE_NAMED_ARG_RE = /(?<=%)%\((\w+)\)([sd])/g;

export function formatPrintfArgs(val, arg) {
    if (arg === 's') return val;
    else if (arg === 'd') return val;
    else {
        // eslint-disable-next-line no-console
        console.error(`Unknown format specifier: ${arg}`);
        return val;
    }
}

export function resolveUnnamed(s, args) {
    let i = 1;
    return s.replace(PYTHON_TEMPLATE_ARG_RE, function(match, typ) {
        i++;
        return formatPrintfArgs(args[i], typ);
    });
}


export function resolveNamed(s, kwargs) {
    return s.replace(PYTHON_TEMPLATE_NAMED_ARG_RE, function(match, name, typ) {
        return formatPrintfArgs(kwargs[name], typ);
    });
}

// used in plugins/upstream/code.py
export function ugettext(s) {
    // Can only have either args (eg %d) or kwargs (eg %(name)s) but not both
    if (PYTHON_TEMPLATE_ARG_RE.test(s)) {
        return resolveUnnamed(s, Array.prototype.slice.call(arguments, 1));
    } else if (PYTHON_TEMPLATE_NAMED_ARG_RE.test(s)) {
        return resolveNamed(s, arguments[arguments.length - 1]);
    } else {
        return s;
    }
}

// used in templates/borrow/read.html
export function ungettext(s1, s2, n, ...args) {
    return n === 1? ugettext(...[s1, ...args]): ugettext(...[s2, ...args]);
}
