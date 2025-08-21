import { buildPartialsUrl } from './utils'
import { PersistentToast } from './Toast'
/**
 * Initializes lazy-loading the "Lists" section of Open Library book pages.
 *
 * @param elem {HTMLElement} Container for book page lists section
 */
export function initListsSection(elem) {
    // Show loading indicator
    const loadingIndicator = elem.querySelector('.loadingIndicator')
    loadingIndicator.classList.remove('hidden')

    const ids = JSON.parse(elem.dataset.ids)

    const intersectionObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Unregister intersection listener
                intersectionObserver.unobserve(entries[0].target)
                fetchPartials(ids.work, ids.edition)
                    .then((resp) => {
                        // Check response code, continue if not 4XX or 5XX

                        return resp.json()
                    })
                    .then((data) => {
                        // Replace loading indicator with partials
                        const listSection = loadingIndicator.parentElement
                        const fragment = document.createDocumentFragment()

                        for (const htmlString of data.partials) {
                            const template = document.createElement('template')
                            template.innerHTML = htmlString
                            fragment.append(...template.content.childNodes)
                        }

                        listSection.replaceChildren(fragment)
                        // Show "See All" link
                        if (data.hasLists) {
                            const showAllLink = elem.querySelector('.lists-heading a')
                            if (showAllLink) {
                                showAllLink.classList.remove('hidden')
                            }
                        }
                        const followForms = listSection.querySelectorAll('.follow-form');
                        initAsyncFollowing(elem, followForms)
                    })
            }
        })
    }, {
        root: null,
        rootMargin: '200px',
        threshold: 0
    })

    intersectionObserver.observe(elem)
}

async function fetchPartials(workId, editionId) {
    const params = {}
    if (workId) {
        params.workId = workId
    }
    if (editionId) {
        params.editionId = editionId
    }

    return fetch(buildPartialsUrl('BPListsSection', params));
}

function initAsyncFollowing(elem, followForms){
    followForms.forEach(form => {
        form.addEventListener('submit', async e => {
            e.preventDefault();
            const stateField = elem.querySelector('input[name=state]');
            const state = stateField.value;
            const publisherField = elem.querySelector('input[name=publisher]');
            const publisher = publisherField.value;
            const redir_urlField = elem.querySelector('input[name=redir_url]');
            const redir_url = redir_urlField.value;
            const url = elem.querySelector('form').action;
            const formData = {
                state: state,
                publisher: publisher,
                redir_url: redir_url,
            };
            fetch(url, {
                method: 'POST',
                body: formData,
                headers: {
                    'content-type': 'application/x-www-form-urlencoded',
                },
            })
                .then(resp => {
                    if (!resp.ok) {
                        // throw an error
                    }
                    followForms.forEach(form => {
                        const publisherField = form.querySelector('input[name=publisher]');
                        const publisher = publisherField.value;
                        if (data.publisher === publisher) {
                            const button = form.querySelector('button');
                            if (button.classList[1] === 'cta-btn--delete') {
                                button.classList.remove('cta-btn--delete');
                                button.classList.add('cta-btn--primary');
                                button.innerText = 'Follow';
                                const state = elem.querySelector('input[name=state]');
                                state.value = 0;
                            }
                            else {
                                button.classList.remove('cta-btn--primary');
                                button.classList.add('cta-btn--delete');
                                button.innerText = 'Unfollow';
                                const state = elem.querySelector('input[name=state]');
                                state.value = 1;
                            }
                        }
                    });
                })
                .catch(() => {
                    // Display toast message
                })
                .finally(() => {
                    // Re-enable the form's submission button
                })
            $.ajax({
                type: 'POST',
                url: url,
                contentType: 'application/x-www-form-urlencoded',
                data: data,
                success: function () {
                    followForms.forEach(form => {
                        const publisherField = form.querySelector('input[name=publisher]');
                        const publisher = publisherField.value;
                        if (data.publisher === publisher) {
                            const button = form.querySelector('button');
                            if (button.classList[1] === 'cta-btn--delete') {
                                button.classList.remove('cta-btn--delete');
                                button.classList.add('cta-btn--primary');
                                button.innerText = 'Follow';
                                const state = elem.querySelector('input[name=state]');
                                state.value = 0;
                            }
                            else {
                                button.classList.remove('cta-btn--primary');
                                button.classList.add('cta-btn--delete');
                                button.innerText = 'Unfollow';
                                const state = elem.querySelector('input[name=state]');
                                state.value = 1;
                            }
                        }
                    });
                },
                error: function () {
                    new PersistentToast('Failed to follow user.  Please try again in a few moments.').show();
                },
            });
        });
    });
}
