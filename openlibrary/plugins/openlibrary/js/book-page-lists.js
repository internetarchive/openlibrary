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
                        // Initialize private buttons after content is loaded
                        initPrivateButtonsAfterLoad(listSection)

                        const followForms = listSection.querySelectorAll('.follow-form');
                        initAsyncFollowing(followForms)
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

async function initAsyncFollowing(followForms) {
    followForms.forEach(form => {
        form.addEventListener('submit', async e => {
            e.preventDefault();
            const url = form.action;
            const formData = new FormData(form);
            const submitButton = form.querySelector('button[type=submit]')
            const stateInput = form.querySelector('input[name=state]')

            const isFollowRequest = stateInput.value === '0'
            const i18nStrings = JSON.parse(submitButton.dataset.i18n)
            submitButton.disabled = true

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
                    submitButton.classList.toggle('cta-btn--primary')
                    submitButton.classList.toggle('cta-btn--delete')
                    submitButton.textContent = isFollowRequest ? i18nStrings.unfollow : i18nStrings.follow
                    stateInput.value = isFollowRequest ? '1' : '0'
                })
                .catch(() => {
                    new PersistentToast(i18nStrings.errorMsg).show();
                })
                .finally(() => {
                    submitButton.disabled = false
                });
        });
    });
}
