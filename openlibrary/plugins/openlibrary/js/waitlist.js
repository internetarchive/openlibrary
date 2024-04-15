/**
 * Initialize the leave waitlist link
 *
 * @param {NodeList<HTMLElement>} leaveWaitlistLinks - NodeList of leave waitlist links
 */
export function initLeaveWaitlist(leaveWaitlistLinks) {
    for (const link of leaveWaitlistLinks) {
        link.addEventListener('click', () => {
            const $link = $(link)
            const title = $link.parents('tr').find('.book').text();
            $('#leave-waitinglist-dialog strong').text(title);
            $('#leave-waitinglist-dialog')
                .data('origin', $link)
                .dialog('open');
        })
    }
}
