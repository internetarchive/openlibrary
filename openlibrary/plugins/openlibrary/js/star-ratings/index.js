import { FadingToast } from '../Toast.js';
import { findDropperForWork } from "../my-books";
import { ReadingLogShelves } from "../my-books/MyBooksDropper/ReadingLogForms";

export function initRatingHandlers(ratingForms) {
    for (const form of ratingForms) {
        form.addEventListener('submit', function(e) {
            handleRatingSubmission(e, form);
        })
    }
}

function handleRatingSubmission(event, form) {
    event.preventDefault();
    // Continue only if selected star is different from previous rating
    if (!event.submitter.classList.contains('star-selected')) {

        // Construct form data object:
        const formData = new FormData(form);
        let rating;
        if (event.submitter.value) {
            rating = Number(event.submitter.value)
            formData.append('rating', event.submitter.value)
        }
        formData.append('ajax', true);

        // Make AJAX call
        fetch(form.action, {
            method: 'POST',
            headers: {
                'content-type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams(formData)
        })
            .then((response) => {
                // POST handler will redirect to login page when not logged in
                if (response.redirected) {
                    window.location = response.url
                }
                if (!response.ok) {
                    throw new Error('Ratings update failed')
                }
                // Update view to deselect all stars
                form.querySelectorAll('.star-selected').forEach((elem) => {
                    elem.classList.remove('star-selected');
                    if (elem.hasAttribute('property')) {
                        elem.removeAttribute('property');
                    }
                })

                const clearButton = form.querySelector('.star-messaging');
                if (rating) {  // A rating was added or updated
                    // Update view to show patron's new star rating:
                    clearButton.classList.remove('hidden');
                    form.querySelectorAll(`.star-${rating}`).forEach((elem) => {
                        elem.classList.add('star-selected');
                        if (elem.tagName === 'LABEL') {
                            elem.setAttribute('property', 'ratingValue')
                        }
                    })

                    // Find dropper that is associated with this star rating affordance:
                    const dropper = findDropperForWork(form.dataset.workKey)
                    if (dropper) {
                        dropper.updateShelfDisplay(ReadingLogShelves.ALREADY_READ)
                    }
                } else {  // A rating was deleted
                    clearButton.classList.add('hidden');
                }
            })
            .catch((error) => {
                new FadingToast(error.message).show();
            })
    }
}
