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

/*
 * Given a hierarchical tree, finds the path from the root to the deepest matching node
 * @template {{ children: T[] }} T
 * @param {T} node
 * @param {(node: T) => boolean} predicate
 * @returns {T[]}
 */
export function hierarchyFind(node, predicate) {
    if (!predicate(node)) return [];
    for (const child of (node.children || [])) {
        const childResult = hierarchyFind(child, predicate);
        if (childResult.length) return [node, ...childResult];
    }
    return [node];
}

/**
 * OBVIOUSLY this is a HUGE simplification; only supports:
 *   - range queries (e.g. `[KJ TO KKZ]`)
 *   - prefix queries (e.g. `0*`)
 * @param {string} pattern
 * @param {string} string
 */
export function testLuceneSyntax(pattern, string) {
    if (pattern.endsWith('*')) {
        return string.startsWith(pattern.slice(0, -1));
    } else if (pattern.endsWith(']')) {
        const [lo, hi] = pattern.slice(1, -1).split(' TO ');
        return string >= lo && string <= hi;
    } else {
        throw new Error(`Unsupported lucene syntax: ${pattern}`);
    }
}

/**
 * @typedef {object} ClassificationNode
 * @property {string} name
 * @property {string} short
 * @property {string} query
 * @property {number} count
 * @property {ClassificationNode[]} children
 * Internal (not in ddc/lcc.json):
 * @property {string | number} position
 * @property {number} offset
 * @property {object} requests
 */

/**
 * @typedef {object} ClassificationTree
 * @property {string} name
 * @property {string} longName
 * @property {string} field
 * @property {(classification: string) => string} fieldTransform
 * @property {(classifications: string[]) => string} chooseBest
 * @property {ClassificationNode} root
 */
