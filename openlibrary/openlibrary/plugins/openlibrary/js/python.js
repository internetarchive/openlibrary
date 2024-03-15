// used in templates/admin/index.html

/**
 * Add commas to a number
 * e.g. 1000 becomes 1,000
 * 1 million becomes 1,000,000
 * @param {mixed} n
 * @return {string}
 */
export function commify(n) {
    var text = n.toString();
    var re = /(\d+)(\d{3})/;

    while (re.test(text)) {
        text = text.replace(re, '$1,$2');
    }

    return text;
}

// Implementation of Python urllib.urlencode in Javascript.
export function urlencode(query) {
    var parts = [];
    var k;
    for (k in query) {
        parts.push(`${k}=${query[k]}`);
    }
    return parts.join('&');
}

export function slice(array, begin, end) {
    var a = [];
    var i;
    for (i=begin; i < Math.min(array.length, end); i++) {
        a.push(array[i]);
    }
    return a;
}
