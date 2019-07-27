/**
 * @this {jQuery}
 */
export default function() {
    return this.find('span.highlight').each(function() {
        var node = this,
            parentNode = node.parentNode;
        parentNode.replaceChild(node.firstChild, node);
        parentNode.normalize();
    }).end();
}
