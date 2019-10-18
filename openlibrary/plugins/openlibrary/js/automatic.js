/**
 * Setup actions on document.ready for standard classNames.
 */
export default function($) {
    var options;
    // Flash messages are hidden by default so that CSS is not on the critical path.
    $('.flash-messages').show();
    // close-popup
    $('a.close-popup').click(function() {
        $.fn.colorbox.close();
    });

    // tabs
    options = {};
    if ($.support.opacity){
        options.fx = {opacity: 'toggle'};
    }

    if ($('.tabs:not(.ui-tabs)').tabs) {
        $('.tabs:not(.ui-tabs)').tabs(options)
        $('.tabs.autohash').bind('tabsselect', function(event, ui) {
            document.location.hash = ui.panel.id;
        });
    }

    // validate forms
    $('form.validate').ol_validate();

    // hide info flash messages
    $('.flash-messages .info').fadeTo(3000, 1).slideUp();

    // hide all images in .no-img
    $('.no-img img').hide();

    // disable save button after click
    $('button[name=\'_save\']').submit(function() {
        $(this).attr('disabled', true);
    });
}
