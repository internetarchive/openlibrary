/**
 * @this {jQuery}
 */
export default function(a, b) {
    return this.each(function() {
        jQuery(this).text(jQuery(this).text() == a ? b : a);
    });
}
