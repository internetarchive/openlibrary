/**
 * Initialize the leave waitlist link
 *
 * @param {NodeList<HTMLElement>} leaveWaitlistLinks - NodeList of leave waitlist links
 */
export function initLeaveWaitlist(leaveWaitlistLinks) {
    $(leaveWaitlistLinks).on('click', () => {
        const title = $(this).parents('tr').find('.book').text();
        $('#leave-waitinglist-dialog strong').text(title);
        $('#leave-waitinglist-dialog')
            .data('origin', $(this))
            .dialog('open');
    });
}
