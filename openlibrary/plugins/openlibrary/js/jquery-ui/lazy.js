function init() {
    return import(
        /* webpackChunkName: "jquery-ui" */
        './index.js'
    );
}

/**
 * Returns a placeholder jQuery UI function which when invoked will
 * load jQuery UI and make the element functional.
 * @param {string} fnName to call when loaded e.g. sortable,tabs,colorbox
 */
function placeholder(fnName) {
    return function () {
        const $this = $(this);
        // only if the selector matches load the additional code and wire it up.
        if ($this.length) {
            init().then(() => {
                if (fnName === 'colorbox') {
                    // set option to open immediately since loading was delayed.
                    arguments[0].open = true;
                }
                // apply it for real now this function has been replaced
                $this[fnName].apply(this, arguments);
            });
        }
        return $this;
    };
}

/**
 * Create a stub of the jQuery UI interface that is conditionally
 * loaded only when needed. The jQuery UI library is large and on the
 * long term we will aim to phase it out. This allows us to do that while
 * not worrying about JS on the critical path.
 * @param {jQuery} $
 */
export default function initJQueryUI($) {
    Object.assign($.fn, {
        tabs: placeholder('tabs'),
        colorbox: placeholder('colorbox'),
        dialog: placeholder('dialog'),
        sortable: placeholder('sortable'),
        disableSelection: placeholder('disableSelection')
    });
}
