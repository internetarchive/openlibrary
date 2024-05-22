/**
 * Setup actions on document.ready for standard classNames.
 */
export default function($) {

    // hide all images in .no-img
    $('.no-img img').hide();

    // disable save button after click
    $('button[name=\'_save\']').on('submit', function() {
        $(this).attr('disabled', true);
    });
}
