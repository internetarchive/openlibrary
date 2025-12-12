// Small module to provide a confirmation modal for delete actions on the edit page.
// Intercepts the `#delete-record` form submission and shows a modal. If the user
// confirms, the original form submission proceeds.
export function initDeleteConfirm() {
    $(function() {
        const $form = $('#delete-record');
        if (!$form.length) return;

        // Confirmation messages for each button
        const MSG_DELETE_ALL = 'Delete the work and ALL its editions? This is irreversible. Click OK to proceed.';
        const MSG_DELETE_EDITION = 'Delete only this edition? This cannot be undone. Click OK to proceed.';

        // Intercept clicks on the specific delete buttons and show the appropriate
        // native confirm dialog. We call `form.submit()` programmatically when
        // the user confirms to ensure the correct behavior.
        $form.find('#delete-all-btn').on('click', function(e) {
            e.preventDefault();
            const btnVal = $(this).val() || 'true';
            if (window.confirm(MSG_DELETE_ALL)) {
                // ensure server receives the same _delete_all param that would be sent
                // if the button were allowed to submit normally
                $form.find('#_delete_temp').remove();
                $('<input>')
                    .attr({type: 'hidden', name: '_delete_all', value: btnVal, id: '_delete_temp'})
                    .appendTo($form);
                $form[0].submit();
            }
        });

        $form.find('#delete-btn').on('click', function(e) {
            e.preventDefault();
            const btnVal = $(this).val() || 'true';
            if (window.confirm(MSG_DELETE_EDITION)) {
                $form.find('#_delete_temp').remove();
                $('<input>')
                    .attr({type: 'hidden', name: '_delete', value: btnVal, id: '_delete_temp'})
                    .appendTo($form);
                $form[0].submit();
            }
        });
    });
}
