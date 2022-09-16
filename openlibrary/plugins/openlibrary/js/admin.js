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

export function initAnonymizationButton(button) {
    const displayName = button.dataset.displayName;
    const confirmMessage = `Really anonymize ${displayName}'s account? This will delete ${displayName}'s profile page and booknotes, and anonymize ${displayName}'s reading log, reviews, star ratings, and merge request submissions.`;
    button.addEventListener('click', function(event) {
        if (!confirm(confirmMessage)) {
            event.preventDefault();
        }
    })
}

/**
 * Adds click listener to each given button.  When the button is clicked,
 * the patron is prompted to confirm the action via a dialog.
 *
 * @param {NodeList<HTMLButtonElement>} buttons
 */
export function initConfirmationButtons(buttons) {
    const confirmMessage = 'Are you sure?'
    for (const button of buttons) {
        button.addEventListener('click', function(event) {
            if (!confirm(confirmMessage)) {
                event.preventDefault();
            }
        })
    }
}
