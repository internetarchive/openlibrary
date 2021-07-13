/**
 * Setup actions on document.ready for standard classNames.
 */
export default function($) {
    // Flash messages are hidden by default so that CSS is not on the critical path.
    $('.flash-messages').show();

    // validate forms
    $('form.validate').ol_validate();

    // hide all images in .no-img
    $('.no-img img').hide();

    // disable save button after click
    $('button[name=\'_save\']').on('submit', function() {
        $(this).attr('disabled', true);
    });
}
