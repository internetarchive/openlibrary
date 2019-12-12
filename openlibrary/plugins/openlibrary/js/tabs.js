const TABS_OPTIONS = { fx: { opacity: 'toggle' } };

export default function initTabs($node) {
    $node.tabs(TABS_OPTIONS);
    $node.filter('.autohash').bind('tabsselect', function(event, ui) {
        document.location.hash = ui.panel.id;
    });
}
