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

/**
 * Drops items whose `keyFn` result was already seen, keeping the first occurrence.
 * @template T
 * @param {T[]} items
 * @param {(item: T) => unknown} keyFn
 * @returns {T[]}
 */
export function uniqBy(items, keyFn) {
    const seen = new Set();
    return items.filter(item => {
        const key = keyFn(item);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

/**
 * Returns the first item with the largest `keyFn` result, or undefined if empty.
 * @template T
 * @param {T[]} items
 * @param {(item: T) => number} keyFn
 * @returns {T | undefined}
 */
export function maxBy(items, keyFn) {
    let best, bestKey;
    items.forEach((item, i) => {
        const key = keyFn(item);
        if (i === 0 || key > bestKey) {
            best = item;
            bestKey = key;
        }
    });
    return best;
}
