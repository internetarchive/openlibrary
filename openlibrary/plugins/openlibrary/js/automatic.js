/**
 * Setup actions on document.ready for standard classNames.
 */
export default function($) {
    // Flash messages are hidden by default so that CSS is not on the critical path.
    $('.flash-messages').show();

    // validate forms
    $('form.validate').ol_validate();

    // hide info flash messages
    $('.flash-messages .info').fadeTo(3000, 1).slideUp();

    // hide all images in .no-img
    $('.no-img img').hide();

    // disable save button after click
    $('button[name=\'_save\']').on('submit', function() {
        $(this).attr('disabled', true);
    });
}
