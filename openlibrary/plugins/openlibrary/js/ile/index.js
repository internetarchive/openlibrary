// @ts-check
import SelectionManager from './utils/SelectionManager/SelectionManager.js';

export function init() {
    const ile = new IntegratedLibrarianEnvironment();
    // @ts-ignore
    window.ILE = ile;
    ile.init();
}

export class IntegratedLibrarianEnvironment {
    constructor() {
        this.selectionManager = new SelectionManager(this);
        /** This is the main ILE toolbar. Should be moved to a Vue component. */
        this.$toolbar = $(`
            <div id="ile-toolbar">
                <div style="flex: 1">
                    <div id="ile-drag-status">
                        <div class="text"></div>
                        <div class="images"></div>
                    </div>
                </div>
                <div id="ile-drag-actions"></div>
            </div>`.trim());
        this.$statusText = this.$toolbar.find('.text');
    }

    init() {
        this.selectionManager.init();

        // Add the ILE toolbar to bottom of screen
        $(document.body).append(this.$toolbar);
    }

    /** @param {string} text */
    setStatusText(text) {
        this.$statusText.text(text);
    }
}
