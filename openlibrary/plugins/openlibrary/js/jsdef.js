/**
 * JavaScript companion for jsdef templetor extension.
 *
 * For more details, see:
 * http://github.com/anandology/notebook/tree/master/2010/03/jsdef/
 */
import { ungettext, ugettext,  sprintf } from './i18n';
// TODO: Can likely move some of these methods into this file
import { commify, urlencode, slice } from './python';
import { truncate, cond } from './utils';

/**
 * Python range function.
 *
 *      > range(2,5)
 *      2,3,4
 *      > range(5)
 *      0,1,2,3,4
 *      > range(0, 10, 2)
 *      0,2,4,6,8
 */

//used in templates/lib/pagination.html
export function range(begin, end, step) {
    var r, i;
    step = step || 1;
    if (end === undefined) {
        end = begin;
        begin = 0;
    }

    r = [];
    for (i=begin; i<end; i += step) {
        r[r.length] = i;
    }
    return r;
}

/**
 * Adds Python's str.join method to Javascript Strings.
 *
 *      > " - ".join(["a", "b", "c"])
 *      a - b - c
 */
export function join(items) {
    return items.join(this);
}

/**
 * Python's len function.
 */

// used in templates/admin/loans.html
export function len(array) {
    return array.length;
}

// used in templates/type/permission/edit.html
export function enumerate(a) {
    var b = new Array(a.length);
    var i;
    for (i in a) {
        b[i] = [i, a[i]];
    }
    return b;
}

export function ForLoop(parent, seq) {
    this.parent = parent;
    this.seq = seq;

    this.length = seq.length;
    this.index0 = -1;
}

ForLoop.prototype.next = function() {
    var i = this.index0+1;

    this.index0 = i;
    this.index = i+1;

    this.first = (i === 0);
    this.last = (i === this.length-1);

    this.odd = (this.index % 2 === 1);
    this.even = (this.index % 2 === 0);
    this.parity = ['even', 'odd'][this.index % 2];

    this.revindex0 = this.length - i;
    this.revindex = this.length - i + 1;
}

// used in plugins/upstream/jsdef.py
export function foreach(seq, parent_loop, callback) {
    var loop = new ForLoop(parent_loop, seq);
    var i, args, j;

    for (i=0; i<seq.length; i++) {
        loop.next();

        args = [loop];

        // case of "for a, b in ..."
        if (callback.length > 2) {
            for (j in seq[i]) {
                args.push(seq[i][j]);
            }
        }
        else {
            args[1] = seq[i];
        }
        callback.apply(this, args);
    }
}

// used in templates/lists/widget.html
export function websafe(value) {
    // Safari 6 is failing with weird javascript error in this function.
    // Added try-catch to avoid it.
    try {
        if (value === null || value === undefined) {
            return '';
        }
        else {
            return htmlquote(value.toString());
        }
    }
    catch (e) {
        return '';
    }
}

/**
 * used in websafe function
 * Quote a string
 * @param {string|number} text to quote
 */
export function htmlquote(text) {
    // This code exists for compatibility with template.js
    text = String(text);
    text = text.replace(/&/g, '&amp;'); // Must be done first!
    text = text.replace(/</g, '&lt;');
    text = text.replace(/>/g, '&gt;');
    text = text.replace(/'/g, '&#39;');
    text = text.replace(/"/g, '&quot;');
    return text;
}

export function is_jsdef() {
    return true;
}


/**
 * foo.get(KEY, default) isn't defined in js, so we can't use that construct
 * in our jsdef methods. This helper function provides a workaround, and works
 * in both environments.
 *
 * @param {object} obj - the object to get the key from
 * @param {string} key - the key to get from the object
 * @param {any} def - the default value to return if the key isn't found
 */
export function jsdef_get(obj, key, def=null) {
    return (key in obj) ? obj[key] : def;
}

export function exposeGlobally() {
    // Extend existing prototypes
    String.prototype.join = join;

    window.commify = commify;
    window.cond = cond;
    window.enumerate = enumerate;
    window.foreach = foreach;
    window.htmlquote = htmlquote;
    window.jsdef_get = jsdef_get;
    window.len = len;
    window.range = range;
    window.slice = slice;
    window.sprintf = sprintf;
    window.truncate = truncate;
    window.urlencode = urlencode;
    window.websafe = websafe;
    window._ = ugettext;
    window.ungettext = ungettext;
    window.uggettext = ugettext;
}
