/**
 * Wires up dialog close buttons
 */
export default function initDialogs() {
    // This will close the dialog in the current page.
    $('.floaterShut').attr('href', 'javascript:;').on('click', () => $.fn.colorbox.close());
    // This will close the colorbox from the parent.
    $('.floaterShut--parent').on('click', () => parent.$.fn.colorbox.close());
}
