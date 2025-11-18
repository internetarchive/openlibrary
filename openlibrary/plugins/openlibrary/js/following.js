import { PersistentToast } from './Toast';

export async function initAsyncFollowing(followForms) {
    followForms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const url = form.action;
            const formData = new FormData(form);
            const submitButton = form.querySelector('button[type=submit]');
            const stateInput = form.querySelector('input[name=state]');

            const isFollowRequest = stateInput.value === '0';
            const i18nStrings = JSON.parse(submitButton.dataset.i18n);
            submitButton.disabled = true;

            await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams(formData)
            })
                .then(resp => {
                    if (!resp.ok) {
                        throw new Error('Network response was not ok');
                    }
                    submitButton.classList.toggle('cta-btn--primary');
                    submitButton.classList.toggle('cta-btn--delete');
                    submitButton.textContent = isFollowRequest ? i18nStrings.unfollow : i18nStrings.follow;
                    stateInput.value = isFollowRequest ? '1' : '0';
                })
                .catch(() => {
                    new PersistentToast(i18nStrings.errorMsg).show();
                })
                .finally(() => {
                    submitButton.disabled = false;
                });
        });
    });
}
