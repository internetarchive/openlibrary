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
