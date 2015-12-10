/**
 * Setup actions on document.ready for standard classNames.
 */

jQuery(function($) {
    // close-popup
    $("a.close-popup").click(function() {
        $.fn.colorbox.close();
    });

    // wmd editor
    $("textarea.markdown").wmd({
        helpLink: "/help/markdown",
        helpHoverTitle: "Formatting Help",
        helpTarget: "_new"
    });

    // tabs
    var options = {};
    if($.support.opacity){
        options.fx = {"opacity": "toggle"};
    }
    $(".tabs:not(.ui-tabs)").tabs(options)
    $(".tabs.autohash")
        .bind("tabsselect", function(event, ui) {
            document.location.hash = ui.panel.id;
        });

    // autocompletes
    $("input.author-autocomplete").author_autocomplete();
    $("input.language-autocomplete").language_autocomplete();

    // validate forms
    $("form.validate").ol_validate();

    // hide info flash messages
    $(".flash-messages .info").fadeTo(3000, 1).slideUp();

    // hide all images in .no-img
    $(".no-img img").hide();
});