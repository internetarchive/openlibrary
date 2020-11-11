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
