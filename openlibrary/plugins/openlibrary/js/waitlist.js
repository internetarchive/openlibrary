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
            // We remove the hidden class here because otherwise it flashes for a moment on page load
            $('#leave-waitinglist-dialog').removeClass('hidden');
            $('#leave-waitinglist-dialog')
                .data('origin', $link)
                .dialog('open');
        })
    }
}
