import { PersistentToast } from './Toast';

export async function initAsyncFollowing(followForms) {
    followForms.forEach(form => {
        form.addEventListener('submit', async(e) => {
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
                    // Sync all follow buttons for the same publisher
                    const publisher = form.querySelector('input[name=publisher]').value;
                    const allFollowForms = document.querySelectorAll('form.follow-form');

                    allFollowForms.forEach(otherForm => {
                        const otherPublisher = otherForm.querySelector('input[name=publisher]');
                        if (otherPublisher && otherPublisher.value === publisher) {
                            const otherButton = otherForm.querySelector('button[type=submit]');
                            const otherStateInput = otherForm.querySelector('input[name=state]');
                            const otherI18n = JSON.parse(otherButton.dataset.i18n);

                            // Set classes explicitly (not toggle) to ensure correct state
                            otherButton.classList.remove('cta-btn--primary', 'cta-btn--delete');
                            otherButton.classList.add(isFollowRequest ? 'cta-btn--delete' : 'cta-btn--primary');
                            otherButton.textContent = isFollowRequest ? otherI18n.unfollow : otherI18n.follow;
                            otherStateInput.value = isFollowRequest ? '1' : '0';
                        }
                    });
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
