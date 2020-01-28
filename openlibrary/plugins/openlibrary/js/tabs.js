const TABS_OPTIONS = { fx: { opacity: 'toggle' } };

/**
 * @param {JQuery} $node one or more tab containers
 */
export default function initTabs($node) {
    if ($node.length > 1) {
        $node.each((i, el) => initTabs($(el)));
        return;
    }

    const $container = $node;
    const autohash = $container.hasClass('autohash');
    const opts = TABS_OPTIONS;
    const panelIdToIndex = {};
    $container.children(':not(:first-child)')
        .each((i, el) => panelIdToIndex[el.id] = i);

    if (autohash) {
        if (location.hash) {
            // skip the hash symbol
            const panelName = location.hash.slice(1);
            opts.active = panelIdToIndex[panelName];
        }
        $container.on('tabsselect', (event, ui) => location.hash = ui.panel.id);
    }

    $container.tabs(opts);
}
