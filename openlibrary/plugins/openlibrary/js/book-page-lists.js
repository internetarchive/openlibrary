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
                        // console.log(listSection)
                        // Show "See All" link
                        if (data.hasLists) {
                            const showAllLink = elem.querySelector('.lists-heading a')
                            if (showAllLink) {
                                showAllLink.classList.remove('hidden')
                            }
                        }
                        const followButtons = listSection.querySelectorAll('.follow-form');
                        // console.log(followButtons)
                        followButtons.forEach(form => {
                            form.addEventListener('submit', async e => {
                                e.preventDefault()
                                // console.log('submit clicked')
                                // const formData = new FormData(form)
                                const stateField = elem.querySelector('input[name=state]');
                                const state = stateField.value
                                const publisherField = elem.querySelector('input[name=publisher]');
                                const publisher = publisherField.value
                                const redir_urlField = elem.querySelector('input[name=redir_url]');
                                const redir_url = redir_urlField.value
                                const url = elem.querySelector('form').action

                                // console.log(publisher)
                                // console.log(state)
                                // console.log(redir_url)
                                // console.log(url)

                                const data = {
                                    state: state,
                                    publisher: publisher,
                                    redir_url: redir_url,
                                }
                                $.ajax({
                                    type: 'POST',
                                    url: url,
                                    contentType: 'application/json',
                                    data: JSON.stringify(data),
                                    dataType: 'json',
                                    beforeSend: function (xhr) {
                                        xhr.setRequestHeader('Content-Type', 'application/json');
                                        xhr.setRequestHeader('Accept', 'application/json');
                                    },
                                    success: function () {
                                        // console.log('successs!!!!')
                                    },
                                    error: function () {
                                        // console.log('failed')
                                    },
                                    complete: function () {
                                        // console.log('completed')
                                    }
                                });

                            })
                        })
                        // followButtons.forEach(button => {
                        //     button.addEventListener('click', () => {
                        //         console.log(button.classList)
                        //         if (button.classList[2].includes('cta-btn--delete')){
                        //             console.log('contains delete')
                        //             button.classList.remove('cta-btn--delete')
                        //             button.classList.add('cta-btn--primary')
                        //         }
                        //     });
                        // });

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
