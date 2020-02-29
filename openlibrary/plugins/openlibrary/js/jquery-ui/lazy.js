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
        // various modules call this methods on non-existent elements.
        // For example the home page doesn't make use of jQuery UI anywhere however without
        // this check will load jQuery UI.
        // This can be removed when that's not the case.
        if ($this.length) {
            init().then(() => {
                console.log('loading for', fnName, $this.length, $this );
                $.fn[fnName].apply($this || this, arguments);
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
    $.fn.extend({
        tabs: placeholder('tabs'),
        colorbox: placeholder('colorbox'),
        dialog: placeholder('dialog'),
        sortable: placeholder('sortable'),
        disableSelection: placeholder('disableSelection')
    });
}
