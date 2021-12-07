export function initRatingHandlers(ratingForms) {
    for (const form of ratingForms) {
        form.addEventListener('submit', function(e) {
            handleRatingSubmission(e, form);
        })
    }
}

function handleRatingSubmission(event, form) {
    event.preventDefault();

    // Construct form data object:
    const formData = new FormData(form);
    if (event.submitter.value) {
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
            // TODO: Repaint stars
            console.log(response)
        })
        .catch((error) => {
            // TODO: Display failure toast
            console.log(error)
        })
}
