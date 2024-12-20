/**
 * These methods are separate from utils.js because that file assumes a globel jQuery object.
 */

/**
 * Debounces func
 * i.e. Returns a function, that, as long as it continues to be invoked, will not
 * be triggered until it stops being called for `threshold` milliseconds. If
 * `execAsap` is passed, trigger the function first, then block it.
 * @param {Function} func
 * @param {Number} [threshold]
 * @param {Boolean} [execAsap]
 * @returns {Function}
 */
export function debounce(func, threshold=100, execAsap=false) {
    let timeout;
    return function debounced() {
        const obj = this, args = arguments;
        function delayed() {
            if (!execAsap)
                func.apply(obj, args);
            timeout = null;
        }

        if (timeout) {
            clearTimeout(timeout);
        } else if (execAsap) {
            func.apply(obj, args);
        }
        timeout = setTimeout(delayed, threshold);
    };
}
