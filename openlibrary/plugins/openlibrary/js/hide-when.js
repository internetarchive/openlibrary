/**
 * A form row that depends on another field's answer: hidden while the radio
 * group named in ``data-hide-when`` has ``data-hide-value`` checked. The row is
 * a fieldset and is disabled while hidden, so the form posts none of its inputs,
 * even ones added later, and the save leaves that field as it was.
 * @param {HTMLFieldSetElement} row - a ``fieldset[data-hide-when]`` inside a form
 * @returns {void}
 */
export function initHideWhen(row) {
    const form = row.closest('form');
    if (!form) return;
    const { hideWhen, hideValue } = row.dataset;
    const sync = () => {
        const checked = form.querySelector(`input[name="${CSS.escape(hideWhen)}"]:checked`);
        row.hidden = checked?.value === hideValue;
        row.disabled = row.hidden;
    };
    form.addEventListener('change', event => {
        if (event.target.name === hideWhen) sync();
    });
    sync();
}

export function init() {
    document.querySelectorAll('fieldset[data-hide-when]').forEach(initHideWhen);
}
