/**
 * Functionalities for templates/subjects and related templates.
 */

import { buildPartialsUrl, createElementFromMarkup, whenVisible } from './utils';

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
    if (!elem.dataset.asyncLoad) {
        return;
    }
    const key = JSON.parse(elem.dataset.key);
    await whenVisible(elem);

    try {
        const resp = await fetch(buildPartialsUrl('SubjectPublishingHistory', {key}));
        if (!resp.ok) {
            throw new Error(`Failed to fetch publishing history partial. Status code: ${resp.status}`);
        }
        const data = await resp.json();
        const newElem = createElementFromMarkup(data.partials);
        elem.replaceWith(newElem);

        const graphs = await import(/* webpackChunkName: "graphs" */ './graphs');
        graphs.initPublishersGraph();
    } catch {
        // XXX : Handle case where `/partials` response is not `2XX` here
    }
}
