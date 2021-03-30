/**
 * Functionality for templates/admin
 */

export function initAdmin() {
    // admin/people/view
    $('a.tag').on('click', function () {
        var action;
        var tag;
        const action_property_str = 'action'
        const tag_property_str = 'tag'

        $(this).toggleClass('active');
        action = $(this).hasClass('active') ? 'add_tag': 'remove_tag';
        tag = $(this).text();
        $.post(window.location.href, {
            action_property_str : action,
            tag_property_str : tag
        });
    });

    // admin/people/edits
    $('#checkall').on('click', function () {
        $('form.olform').find(':checkbox').attr('checked', this.checked);
    });
}
