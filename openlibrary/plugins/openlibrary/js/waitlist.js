import { confirmFromTemplate } from './confirm-template';

/**
 * Initialize the leave waitlist link
 *
 * @param {NodeList<HTMLElement>} leaveWaitlistLinks - NodeList of leave waitlist links
 */
export function initLeaveWaitlist(leaveWaitlistLinks) {
    const template = document.getElementById('leave-waitinglist-dialog');
    for (const link of leaveWaitlistLinks) {
        link.addEventListener('click', async(event) => {
            event.preventDefault();
            const message = template.content.cloneNode(true);
            message.querySelector('strong').textContent = link.closest('tr').querySelector('.book').textContent.trim();
            if (await confirmFromTemplate(template, { message })) {
                link.closest('form').requestSubmit();
            }
        });
    }
}
