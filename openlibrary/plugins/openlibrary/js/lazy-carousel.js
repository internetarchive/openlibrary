import {initialzeCarousels} from './carousel';

/**
 * Adds functionality that allows carousels to lazy-load when a patron
 * scrolls near any of the given elements
 *
 * @param elems {NodeList<HTMLElement>} Collection of placeholder carousel elements
 */
export function initLazyCarousel(elems) {
    // Create intersection observer
    const intersectionObserver = new IntersectionObserver(intersectionCallback, {
        root: null,
        rootMargin: '200px',
        threshold: 0
    })

    elems.forEach(elem => {
        // Observe element for intersections
        intersectionObserver.observe(elem)

        // Add retry listener
        const retryElem = elem.querySelector('.retry-btn')
        retryElem.addEventListener('click', (e) => {
            e.preventDefault()
            handleRetry(elem)
        })
    })
}

/**
 * Prepares and makes a request for carousel HTML>
 *
 * @param data {object}
 * @returns {Promise<Response>}
 */
async function fetchPartials(data) {
    const searchParams = new URLSearchParams({...data, _component: 'LazyCarousel'})
    return fetch(`/partials.json?${searchParams.toString()}`)
}

/**
 * Attempts to fetch HTML for a single carousel, and updates the view
 * with the results.
 *
 * If the request is successful, the given `target` element is replaced
 * by the carousel.  Otherwise, a retry button is presented to the patron.
 *
 * On retry, this function is called again.
 *
 * @param target {HTMLElement} A placeholder element for a carousel
 */
function doFetchAndUpdate(target) {
    const config = JSON.parse(target.dataset.config)
    fetchPartials(config)
        .then(resp => {
            if (!resp.ok) {
                throw new Error('Failed to fetch partials from server')
            }
            return resp.json()
        })
        .then(data => {
            const newElem = document.createElement('div')
            newElem.innerHTML = data.partials.trim()
            target.parentNode.insertBefore(newElem, target)
            target.remove()
            const carouselElements = newElem.querySelectorAll('.carousel--progressively-enhanced')
            initialzeCarousels(carouselElements)
        })
        .catch(() => {
            const loadingIndicator = target.querySelector('.loadingIndicator')
            loadingIndicator.classList.add('hidden')
            const retryElem = target.querySelector('.lazy-carousel-retry')
            retryElem.classList.remove('hidden')
        })
}

/**
 * Shows loading indicator, hides retry element, and attempts to
 * fetch data and update the view again.
 *
 * @param target {Element}
 */
function handleRetry(target) {
    const loadingIndicator = target.querySelector('.loadingIndicator')
    const retryElem = target.querySelector('.lazy-carousel-retry')
    loadingIndicator.classList.remove('hidden')
    retryElem.classList.add('hidden')
    doFetchAndUpdate(target)

}

/**
 * Callback used by the lazy-loaded carousel intersection observer.
 *
 * Unregisters target from observer and fetches carousel HTML.
 *
 * @param entries {Array<IntersectionObserverEntry>}
 * @param observer {IntersectionObserver}
 */
function intersectionCallback(entries, observer) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const target = entry.target
            observer.unobserve(target)
            doFetchAndUpdate(target)
        }
    })
}
