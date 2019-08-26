function init() {
    return import(
        /* webpackChunkName: "ui" */
        './ui'
    );
}

/**
 * Returns a placeholder jQuery UI function which when invoked will
 * load jQuery UI and make the element functional.
 * @param {string} fnName to call when loaded e.g. sortable,tabs,colorbox
 */
export function placeholder(fnName) {
    return function () {
        // only if the selector matches load the additional code and wire it up.
        if ($(this).length) {
            init().then(() => {
                // apply it for real now this function has been replaced
                $(this)[fnName].apply(this, arguments);
            });
        }
        return $(this);
    };
}
