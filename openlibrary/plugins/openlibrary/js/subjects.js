/**
 * Functionalities for templates/subjects and related templates.
 */

import { fetchAndSwap } from './utils';

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
    await fetchAndSwap(elem, 'SubjectPublishingHistory', async() => {
        const graphs = await import('./graphs');
        graphs.initPublishersGraph();
    });
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
