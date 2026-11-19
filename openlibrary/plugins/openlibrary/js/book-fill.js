/**
 * Filling in an empty field from the book page.
 *
 * An empty field's slot holds an "Add" button (`[data-book-fill]`). It opens a
 * modeless drawer beside the record and loads that field's form into it from
 * `/tasks/fill/OL…M/<field>`; the form posts back to the same address, and the
 * answer saves as a normal edit. The slot then shows the new value, so the page
 * matches the record without a reload.
 */
import { trackEvent } from './ol.analytics.js';

/** Matches the drawer's sheet breakpoint: no focus into a text field there, or the keyboard covers the sheet. */
const PHONE = '(max-width: 767px)';

/**
 * Put focus on the answer once a form is in the drawer, so a keyboard user can type straight away.
 * @param {HTMLElement} body - the drawer's content
 * @returns {void}
 */
function focusAnswer(body) {
    if (window.matchMedia(PHONE).matches) return;
    body.querySelector('[data-book-fill-answer]')?.focus({ preventScroll: true });
}

/**
 * Wire the "Other editions say" chips to the answer: picking one fills it in, and picking it again clears it.
 * @param {HTMLElement} body - the drawer's content
 * @returns {void}
 */
function initSuggestions(body) {
    const group = body.querySelector('[data-book-fill-suggest]');
    const answer = body.querySelector('[data-book-fill-answer]');
    if (!group || !answer) return;
    const isPicker = answer.tagName === 'OL-OPTIONS-POPOVER';
    const read = () => (isPicker ? answer.selected : answer.value.trim());
    const chips = [...group.querySelectorAll('ol-chip')];
    const sync = () =>
        chips.forEach(chip => {
            chip.selected = chip.dataset.value === read();
        });
    group.addEventListener('ol-chip-select', event => {
        const value = event.detail.selected ? event.target.closest('ol-chip').dataset.value : '';
        if (isPicker) answer.selected = value;
        else answer.value = value;
        sync();
        if (value) trackEvent('BookFill', 'PickSuggestion', body.querySelector('[data-book-fill-panel]').dataset.field);
    });
    answer.addEventListener(isPicker ? 'ol-options-popover-change' : 'input', sync);
    sync();
}

/**
 * Show a dealt-with field on the page: its new value in the slot, or the slot gone when the reader couldn't find one.
 * @param {HTMLElement} done - the drawer's `[data-book-fill-done]` panel
 * @returns {void}
 */
function settleSlot(done) {
    const slot = document.querySelector(`[data-book-fill-slot="${done.dataset.field}"]`);
    if (!slot) return;
    if (done.dataset.bookFillDone !== 'saved') {
        slot.remove();
        return;
    }
    const value = document.createElement('span');
    value.textContent = done.dataset.value;
    slot.querySelector('ol-button').replaceWith(value);
    slot.classList.remove('edition-omniline-item--empty');
    slot.removeAttribute('data-book-fill-slot');
}

/**
 * @param {HTMLElement} drawer - the page's `ol-drawer[data-book-fill-drawer]`
 * @returns {void}
 */
function initDrawer(drawer) {
    const body = drawer.querySelector('[data-book-fill-body]');
    // Not in the top layer, so it sits on <body>, clear of any transformed ancestor.
    document.body.appendChild(drawer);
    /** Bumped per request, so a slow response can't overwrite the field opened after it. */
    let request = 0;

    const showMessage = text => {
        const message = document.createElement('p');
        message.className = 'ol-message ol-message--error';
        message.setAttribute('role', 'alert');
        message.textContent = text;
        const form = body.querySelector('[data-book-fill-form]');
        form?.querySelector('.ol-message')?.remove();
        if (form) form.prepend(message);
        else body.replaceChildren(message);
    };

    /**
     * Put a response's panel in the drawer. Returns false when there was none to show.
     * @param {Response} response
     * @param {number} mine - the request this response answers
     */
    const show = async (response, mine) => {
        if (response.status === 401) {
            showMessage(drawer.dataset.msgLogin);
            return false;
        }
        // 422 is the form again, with what was wrong.
        if (!response.ok && response.status !== 422) throw new Error(`Book fill: ${response.status}`);
        const html = await response.text();
        if (mine !== request) return false;
        // Server-rendered and escaped by Jinja; the same origin's own markup.
        body.innerHTML = html;
        const done = body.querySelector('[data-book-fill-done]');
        if (done) settleSlot(done);
        else initSuggestions(body);
        return true;
    };

    const open = async field => {
        const mine = ++request;
        body.replaceChildren();
        drawer.setAttribute('aria-busy', 'true');
        drawer.open = true;
        try {
            const response = await fetch(`${drawer.dataset.url}/${field}`, { headers: { Accept: 'text/html' } });
            if (await show(response, mine)) focusAnswer(body);
        } catch {
            if (mine === request) showMessage(drawer.dataset.msgError);
        } finally {
            if (mine === request) drawer.removeAttribute('aria-busy');
        }
    };

    document.addEventListener('click', event => {
        const trigger = event.target.closest('[data-book-fill]');
        if (trigger) open(trigger.dataset.bookFill);
        else if (event.target.closest('[data-book-fill-close]')) drawer.open = false;
    });

    body.addEventListener('submit', async event => {
        const form = event.target.closest('[data-book-fill-form]');
        if (!form) return;
        event.preventDefault();
        const mine = ++request;
        const field = form.closest('[data-book-fill-panel]').dataset.field;
        const pressed = event.submitter?.closest('ol-button');
        const buttons = form.querySelectorAll('ol-button[type="submit"]');
        // Read before the buttons disable: a loading ol-button disables the proxy that carries `then`.
        const data = new URLSearchParams(new FormData(form, event.submitter));
        buttons.forEach(button => {
            button.loading = button === pressed;
            button.disabled = button !== pressed;
        });
        try {
            const response = await fetch(form.action, { method: 'POST', body: data, headers: { Accept: 'text/html' } });
            const shown = await show(response, mine);
            const done = body.querySelector('[data-book-fill-done]');
            if (shown && done?.dataset.bookFillDone === 'saved') trackEvent('BookFill', 'Save', field);
            if (shown)
                (done ? body.querySelector('.book-fill__actions [data-book-fill-close]') : body.querySelector('[data-book-fill-answer]'))?.focus({
                    preventScroll: true
                });
        } catch {
            if (mine === request) showMessage(drawer.dataset.msgError);
        } finally {
            // A replaced form took its buttons with it; these are the ones still on screen after a failure.
            buttons.forEach(button => {
                button.loading = false;
                button.disabled = false;
            });
        }
    });
}

export function init() {
    document.querySelectorAll('ol-drawer[data-book-fill-drawer]').forEach(initDrawer);
}
