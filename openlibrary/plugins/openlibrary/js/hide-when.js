/**
 * A form row that depends on another field's answer: hidden while the radio
 * group named in ``data-hide-when`` has ``data-hide-value`` checked. Its inputs
 * are disabled while hidden, so the form doesn't post them and the save leaves
 * that field as it was.
 * @param {HTMLElement} row - a ``[data-hide-when]`` element inside a form
 * @returns {void}
 */
export function initHideWhen(row) {
    const form = row.closest('form');
    if (!form) return;
    const { hideWhen, hideValue } = row.dataset;
    const sync = () => {
        const checked = form.querySelector(`input[name="${CSS.escape(hideWhen)}"]:checked`);
        row.hidden = checked?.value === hideValue;
        row.querySelectorAll('input').forEach(input => (input.disabled = row.hidden));
    };
    form.addEventListener('change', event => {
        if (event.target.name === hideWhen) sync();
    });
    // Again on submit: the chips add their hidden inputs after load. The form data is read after this event.
    form.addEventListener('submit', sync);
    sync();
}

export function init() {
    document.querySelectorAll('[data-hide-when]').forEach(initHideWhen);
}
