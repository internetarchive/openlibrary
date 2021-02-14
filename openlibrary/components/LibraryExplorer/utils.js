// @ts-check

/**
 * @template {{ children: T[] }} T
 * @param {T} node
 * @param {(node: T) => void} fn
 */
export function recurForEach(node, fn) {
    if (!node) return;
    fn(node);
    if (!node.children) return;
    for (const child of node.children) {
        recurForEach(child, fn);
    }
    return node;
}

/**
 * Src: https://stackoverflow.com/a/3426956/2317712
 * @param {string} str
 */
export function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return hash;
}
