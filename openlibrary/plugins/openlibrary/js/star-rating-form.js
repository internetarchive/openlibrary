// @ts-check
import { FadingToast } from './Toast.js';

export class StarRatingForm {
    /**
     * @param {HTMLFormElement} form
     */
    constructor(form) {
        /** @type {HTMLFormElement} */
        this.form = form;
    }

    attach() {
        this.form.addEventListener('submit', (event) => {
            // Have to do before the async function, otherwise
            // it'll be too late to prevent the default action
            event?.preventDefault();
            this.handleSubmission(event);
        });
    }

    /**
     * @param {SubmitEvent} event
     */
    async handleSubmission(event) {
        event.preventDefault();

        // Ignore if already selected
        if (event.submitter.classList.contains('star-selected')) {
            return;
        }

        // Note this can be null if the clear ratings button is pressed.
        // The is not an input element
        const newRating = parseFloat(event.submitter.value || '0');

        try {
            const response = await fetch(this.form.action, {
                method: 'POST',
                headers: {
                    'content-type': 'application/x-www-form-urlencoded'
                },
                body: new URLSearchParams({
                    ...(newRating ? { rating: newRating.toString() } : {}),
                    ajax: 'true',
                })
            });

            // POST handler will redirect to login page when not logged in
            if (response.redirected) {
                window.location = response.url
            }
            if (!response.ok) {
                throw new Error('Ratings update failed')
            }

            // Reset all stars
            this.form.querySelectorAll('.star-selected').forEach((elem) => {
                elem.classList.remove('star-selected');
                if (elem.hasAttribute('property')) {
                    elem.removeAttribute('property');
                }
            });
            $(this.form).find('.star.yellow').removeClass('yellow');

            // Set new stars
            this.form.querySelectorAll('.star input').forEach((inpt) => {
                const value = parseFloat(inpt.value);
                if (value <= newRating) {
                    inpt.parentElement.classList.add('yellow');
                }
                if (value === newRating) {
                    inpt.classList.add('star-selected');
                    inpt.parentElement.classList.add('star-selected');
                    inpt.parentElement.setAttribute('property', 'ratingValue');
                }
            });

            const clearButton = this.form.querySelector('.clear-rating');
            clearButton.classList.toggle('hidden', !newRating);
        } catch (error) {
            new FadingToast(error.message).show();
        }
    }
}
