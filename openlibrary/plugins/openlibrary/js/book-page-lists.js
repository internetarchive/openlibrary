import { buildPartialsUrl } from './utils'

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
                        // Initialize private buttons after content is loaded
                        initPrivateButtonsAfterLoad(listSection)
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

/**
 * Initialize private buttons after the lists section has been loaded
 * @param {HTMLElement} container - The container that now has the loaded content
 */
function initPrivateButtonsAfterLoad(container) {
    const privateButtons = container.querySelectorAll('.list-follow-card__private-button')
    if (privateButtons.length > 0) {
        import(/* webpackChunkName: "private-buttons" */ './private-button')
            .then(module => {
                module.initPrivateButtons(privateButtons)
            })
    }
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
async function initAsyncFollowing(elem, followForms) {
    followForms.forEach(form => {
        form.addEventListener('submit', async e => {
            e.preventDefault();
            const url = form.action;
            const formData = new FormData(form);
            const publisherField = form.querySelector('input[name=publisher]');
            const publisher = publisherField.value;
            fetch(url, {
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
                    followForms.forEach(followForm => {
                        const publisherField = followForm.querySelector('input[name=publisher]');
                        if (publisherField.value === publisher) {
                            const followButton = followForm.querySelector('button');
                            const i18nStrings = JSON.parse(followButton.dataset.i18n)
                            followButton.disabled = true;
                            if (followButton.classList.contains('cta-btn--delete')) {
                                followButton.classList.remove('cta-btn--delete');
                                followButton.classList.add('cta-btn--primary');
                                followButton.innerText = i18nStrings.follow
                            }
                            else {
                                followButton.classList.remove('cta-btn--primary');
                                followButton.classList.add('cta-btn--delete');
                                followButton.innerText = i18nStrings.unfollow
                            }
                            const stateInput = elem.querySelector('input[name=state]');
                            stateInput.value = 1 - stateInput.value;
                        }
                    });
                })
                .catch((error) => {
                    new PersistentToast('Failed to update followers.  Please try again in a few moments.').show();
                })
                .finally(() => {
                    followForms.forEach(followForm => {
                        const publisherField = followForm.querySelector('input[name=publisher]');
                        if (publisherField.value === publisher) {
                            const followButton = followForm.querySelector('button');
                            followButton.disabled = false;
                        }
                    });
                });
        });
    });
}
