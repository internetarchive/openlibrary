const TABS_OPTIONS = { fx: { opacity: 'toggle' } };
import 'jquery-ui/ui/widgets/tabs';

export function initTabs($node) {
    $node.tabs(TABS_OPTIONS);
    $node.filter('.autohash').on('tabsselect', function(event, ui) {
        document.location.hash = ui.panel.id;
    });
}
