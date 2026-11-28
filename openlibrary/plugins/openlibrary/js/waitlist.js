import { confirmFromTemplate } from './confirm-template';
import { _ } from './i18n.js';

/**
 * Initialize the leave waitlist link
 *
 * @param {NodeList<HTMLElement>} leaveWaitlistLinks - NodeList of leave waitlist links
 */
export function initLeaveWaitlist(leaveWaitlistLinks) {
    const template = document.getElementById('leave-waitinglist-dialog');
    for (const link of leaveWaitlistLinks) {
        link.addEventListener('click', async event => {
            event.preventDefault();
            const message = template.content.cloneNode(true);
            message.querySelector('strong').textContent = link.closest('tr').querySelector('.book').textContent.trim();
            if (await confirmFromTemplate(template, { message, title: _('Leave the waiting list?'), confirmLabel: _('Leave waiting list') })) {
                link.closest('form').requestSubmit();
            }
        });
    }
}
