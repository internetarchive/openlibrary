/**
 * Functionality for templates/admin
 */

export function initAdmin() {
    // admin/people/view
    for (const link of document.querySelectorAll('a.tag')) {
        link.addEventListener('click', function () {
            this.classList.toggle('active');
            const action = this.classList.contains('active') ? 'add_tag' : 'remove_tag';
            fetch(window.location.href, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ action, tag: this.textContent })
            });
        });
    }

    // admin/people/edits
    document.getElementById('checkall')?.addEventListener('click', function () {
        for (const box of document.querySelectorAll('form.olform input[type=checkbox]')) {
            box.checked = this.checked;
        }
    });
}

export function initAnonymizationButton(button) {
    const displayName = button.dataset.displayName;
    const confirmMessage = `Really anonymize ${displayName}'s account? This will delete ${displayName}'s profile page and booknotes, and anonymize ${displayName}'s reading log, reviews, star ratings, and merge request submissions.`;
    button.addEventListener('click', function (event) {
        if (!confirm(confirmMessage)) {
            event.preventDefault();
        }
    });
}

/**
 * Adds click listener to each given button.  When the button is clicked,
 * the patron is prompted to confirm the action via a dialog.
 *
 * @param {NodeList<HTMLButtonElement>} buttons
 */
export function initConfirmationButtons(buttons) {
    const confirmMessage = 'Are you sure?';
    for (const button of buttons) {
        button.addEventListener('click', function (event) {
            if (!confirm(confirmMessage)) {
                event.preventDefault();
            }
        });
    }
}

/**
 * /admin/new-accounts: tick rows (shift-click ticks a range), then act on all of them.
 * The bulk buttons wait for a selection and confirm with their `data-confirm` text.
 * @param {HTMLFormElement} form
 */
export function initNewAccountsReview(form) {
    const boxes = [...form.querySelectorAll('input[name="username"]')];
    const all = form.querySelector('.new-accounts__select-all');
    const status = form.querySelector('.new-accounts__selected');
    const actions = form.querySelectorAll('.new-accounts__bulk-action');
    const { selectAll, selectedCount } = status.dataset;
    let last = null;

    const update = () => {
        const count = boxes.filter(box => box.checked).length;
        all.checked = count > 0 && count === boxes.length;
        all.indeterminate = count > 0 && count < boxes.length;
        status.textContent = count ? selectedCount.replace('__COUNT__', count) : selectAll;
        for (const action of actions) action.disabled = !count;
        for (const box of boxes) box.closest('tr').classList.toggle('new-accounts__row--selected', box.checked);
    };

    all.addEventListener('change', () => {
        for (const box of boxes) box.checked = all.checked;
        update();
    });
    form.addEventListener('click', event => {
        const box = event.target;
        if (!boxes.includes(box)) return;
        if (event.shiftKey && last) {
            const [from, to] = [boxes.indexOf(last), boxes.indexOf(box)].sort((a, b) => a - b);
            for (const other of boxes.slice(from, to + 1)) other.checked = box.checked;
        }
        last = box;
        update();
    });
    form.addEventListener('submit', event => {
        const message = event.submitter?.closest('ol-button')?.dataset.confirm;
        if (message && !confirm(message)) event.preventDefault();
    });
    update();
}

/**
 * /admin/new-accounts: picking a window in the "Edited in the last" control reloads the page with it.
 * @param {HTMLFormElement} form
 */
export function initNewAccountsWindow(form) {
    // The event fires before the control's form value updates, so the URL is built from the event.
    form.addEventListener('ol-segmented-control-change', event => {
        const params = new URLSearchParams(new FormData(form));
        params.set('hours', event.detail.value);
        location.search = params.toString();
    });
}
