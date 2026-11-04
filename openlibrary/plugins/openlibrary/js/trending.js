/**
 * /trending: the period control under Most Shelved is navigation, not a filter
 * in place. Each period is its own page, so a change loads it.
 *
 * @param {HTMLElement} control The <ol-segmented-control> of periods
 */
export function initTrendingPeriods(control) {
    control.addEventListener('ol-segmented-control-change', event => {
        window.location.assign(`/trending/${event.detail.value}`);
    });
}
