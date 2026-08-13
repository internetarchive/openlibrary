/**
 * Functionalities for templates/subjects and related templates.
 */

import { buildPartialsUrl, createElementFromMarkup, whenVisible } from './utils';

/**
 * Once `elem` is visible, fetches `component`'s real markup (keyed off
 * `elem.dataset.key`) and replaces `elem` with it.
 *
 * @param {HTMLElement} elem Root element of an async-loaded subject component
 * @param {string} component Partial component name (e.g. 'SubjectRelated')
 * @returns {Promise<HTMLElement | null>} The element that replaced `elem`, or null on failure
 */
async function fetchAndSwap(elem, component) {
    if (!elem.dataset.asyncLoad) {
        return null;
    }
    const key = JSON.parse(elem.dataset.key);
    await whenVisible(elem);

    try {
        const resp = await fetch(buildPartialsUrl(component, {key}));
        if (!resp.ok) {
            throw new Error(`Failed to fetch ${component} partial. Status code: ${resp.status}`);
        }
        const data = await resp.json();
        const newElem = createElementFromMarkup(data.partials);
        elem.replaceWith(newElem);
        return newElem;
    } catch {
        // XXX : Handle case where `/partials` response is not `2XX` here
        return null;
    }
}

/**
 * Initializes the subject page's publishing-history chart.
 *
 * The chart initially contains a loading indicator instead of a graph. Once
 * visible, a request is made for the chart's real markup (with the
 * publish_year facet data baked in), the placeholder is replaced with it,
 * and the flot chart is drawn against the newly-inserted markup.
 *
 * @param {HTMLElement} elem Root element of the publishing-history component
 */
export async function initPublishingHistory(elem) {
    if (await fetchAndSwap(elem, 'SubjectPublishingHistory')) {
        const graphs = await import(/* webpackChunkName: "graphs" */ './graphs');
        graphs.initPublishersGraph();
    }
}

/**
 * Initializes the subject page's related subjects/places/people/times widget.
 *
 * Each category initially contains a loading indicator. Once visible, a
 * request is made for the widget's real markup, and the placeholder is
 * replaced with it.
 *
 * @param {HTMLElement} elem Root element of the related-subjects component
 */
export async function initRelatedSubjects(elem) {
    await fetchAndSwap(elem, 'SubjectRelated');
}
