/**
 * Functionality for templates/admin
 */

export function initAdmin() {
    // admin/people/view
    $('a.tag').on('click', function () {
        var action;
        var tag;

        $(this).toggleClass('active');
        action = $(this).hasClass('active') ? 'add_tag': 'remove_tag';
        tag = $(this).text();
        $.post(window.location.href, {
            action: action,
            tag: tag
        });
    });

    // admin/people/edits
    $('#checkall').on('click', function () {
        $('form.olform').find(':checkbox').prop('checked', this.checked);
    });
}
