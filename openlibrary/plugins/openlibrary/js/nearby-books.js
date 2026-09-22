import {initialzeCarousels} from './carousel';
import { buildPartialsUrl, whenVisible } from './utils';

/**
 * Adds functionality that allows the "Nearby Books" carousel to lazy-load
 * when a patron scrolls near it, fetching its HTML from
 * /partials/NearbyBooks.json (see openlibrary/fastapi/partials.py).
 *
 * @param elems {NodeList<HTMLElement>} Collection of placeholder elements
 */
export function initNearbyBooks(elems) {
    elems.forEach(elem => {
        whenVisible(elem).then(() => doFetchAndUpdate(elem));

        const retryElem = elem.querySelector('.retry-btn');
        retryElem.addEventListener('click', (e) => {
            e.preventDefault();
            handleRetry(elem);
        });
    });
}

/**
 * Fetches HTML for the carousel and updates the view with the results.
 *
 * If Solr has no neighbouring books (or the request fails), the placeholder
 * is simply removed so it doesn't take up layout space; on request failure a
 * retry affordance is shown instead.
 *
 * @param target {HTMLElement} A placeholder element for the carousel
 */
function doFetchAndUpdate(target) {
    const { language, workKey } = target.dataset;
    const loadingIndicator = target.querySelector('.loadingIndicator');

    fetch(buildPartialsUrl('NearbyBooks', { work_key: workKey, language }))
        .then(resp => {
            if (!resp.ok) {
                throw new Error('Failed to fetch partials from server');
            }
            return resp.json();
        })
        .then(data => {
            loadingIndicator.classList.add('hidden');

            const newElem = document.createElement('div');
            newElem.className = 'nearby-books-loaded';
            newElem.innerHTML = (data.partials || '').trim();
            const carouselElements = newElem.querySelectorAll('.carousel--progressively-enhanced');

            if (carouselElements.length === 0) {
                target.remove();
            } else {
                target.parentNode.insertBefore(newElem, target);
                target.remove();
                initialzeCarousels(carouselElements);
            }
        })
        .catch(() => {
            loadingIndicator.classList.add('hidden');
            target.querySelector('.nearby-books-retry').classList.remove('hidden');
        });
}

/**
 * Shows loading indicator, hides retry element, and attempts to
 * fetch data and update the view again.
 *
 * @param target {Element}
 */
function handleRetry(target) {
    target.querySelector('.loadingIndicator').classList.remove('hidden');
    target.querySelector('.nearby-books-retry').classList.add('hidden');
    doFetchAndUpdate(target);
}
