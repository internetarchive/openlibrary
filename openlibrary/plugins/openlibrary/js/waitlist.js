/**
 * Initialize the leave waitlist link
 *
 * @param {NodeList<HTMLElement>} waitlistLinks - NodeList of leave waitlist links
 */
export function initLeaveWaitlist(waitlistLinks) {
    $(waitlistLinks).on('click', function() {
        const title = $(this).parents('tr').find('.book').text();
        $('#leave-waitinglist-dialog strong').text(title);
        $('#leave-waitinglist-dialog')
            .data('origin', $(this))
            .dialog('open');
    });
}
