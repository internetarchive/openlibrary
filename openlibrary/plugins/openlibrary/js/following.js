import { showToast } from '../../../components/lit/toast.js';
import { _ } from './i18n.js';

export async function initAsyncFollowing(followForms) {
    followForms.forEach(form => {
        form.addEventListener('submit', async e => {
            e.preventDefault();
            const url = form.action;
            const formData = new FormData(form);
            const submitButton = form.querySelector('button[type=submit]');
            const stateInput = form.querySelector('input[name=state]');

            const isFollowRequest = stateInput.value === '0';
            submitButton.disabled = true;

            await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: new URLSearchParams(formData)
            })
                .then(resp => {
                    if (!resp.ok) {
                        throw new Error('Network response was not ok');
                    }
                    submitButton.classList.toggle('cta-btn--primary');
                    submitButton.classList.toggle('cta-btn--delete');
                    submitButton.textContent = isFollowRequest ? _('Unfollow') : _('Follow');
                    stateInput.value = isFollowRequest ? '1' : '0';
                })
                .catch(() => {
                    showToast(_('Failed to update followers. Please try again in a few moments.'), { type: 'error', persistent: true });
                })
                .finally(() => {
                    submitButton.disabled = false;
                });
        });
    });
}
