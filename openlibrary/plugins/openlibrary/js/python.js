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
