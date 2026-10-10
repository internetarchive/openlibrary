/**
 * Open Library Tasks (/tasks) page behavior.
 *
 * Saved tasks leave the list on the server. Skipped ones are remembered for
 * the browser session so they drop out of the list too.
 */

import { parseLccn, isValidLccn, parseOclc, isValidOclc } from './idValidation';

const SKIPPED_KEY = 'ol-contribute-skipped';

// Same normalization the server applies, so the verdict on screen matches what is stored.
const ID_RULES = {
    lccn: { parse: parseLccn, isValid: isValidLccn },
    oclc_numbers: { parse: parseOclc, isValid: isValidOclc },
};

/**
 * The task keys skipped this browser session.
 * @returns {Set<string>} the stored skipped-task keys (empty if none/unavailable)
 */
function readSkippedTaskKeys() {
    try {
        return new Set(JSON.parse(sessionStorage.getItem(SKIPPED_KEY) || '[]'));
    } catch (e) {
        return new Set();
    }
}

/**
 * Remember a task as skipped for this browser session.
 * @param {string} key - the task key (``OL…M/<field>``) to mark skipped
 * @returns {void}
 */
function markTaskSkipped(key) {
    const skipped = readSkippedTaskKeys();
    skipped.add(key);
    try {
        sessionStorage.setItem(SKIPPED_KEY, JSON.stringify([...skipped]));
    } catch (e) {
        // Blocked storage: the skipped task just stays listed.
    }
}

/**
 * Hide skipped tasks, then any group (book row, same-book section) left with none.
 * @param {ParentNode} root - the subtree to hide within
 * @param {string} groupSelector - selector for the grouping element to collapse when empty
 * @returns {void}
 */
function hideSkippedTasks(root, groupSelector) {
    const skipped = readSkippedTaskKeys();
    root.querySelectorAll('[data-task-key]').forEach((el) => {
        if (skipped.has(el.dataset.taskKey)) el.hidden = true;
    });
    root.querySelectorAll(groupSelector).forEach((group) => {
        if (!group.querySelector('[data-task-key]:not([hidden])')) group.hidden = true;
    });
}

/**
 * Hide skipped rows in the dashboard list and toggle its empty state.
 * @param {ParentNode} root - the ``[data-contribute-list]`` container
 * @returns {void}
 */
function initTaskList(root) {
    hideSkippedTasks(root, '[data-book-row]');
    const empty = root.querySelector('[data-list-empty]');
    if (empty) empty.hidden = !!root.querySelector('[data-book-row]:not([hidden])');
}

/**
 * Remember this task as skipped when its "I couldn't find it" control is clicked.
 * @param {HTMLFormElement} form - a ``[data-task-form]`` whose ``data-task-key`` identifies the task
 * @returns {void}
 */
function initSkipButton(form) {
    form.querySelector('[data-skip]')?.addEventListener('click', () => markTaskSkipped(form.dataset.taskKey));
}

/**
 * Wire the "Other editions say" chips to the answer control. The chip matching
 * the current answer shows selected; clicking it again clears it.
 * @param {HTMLFormElement} form - the task form holding the chips and answer control
 * @returns {void}
 */
function initSiblingSuggestions(form) {
    const group = form.querySelector('[data-suggest]');
    const control = form.querySelector('#contrib-other-value');
    if (!group || !control) return;
    const isPicker = control.tagName === 'OL-OPTIONS-POPOVER';
    const currentAnswer = () => (isPicker ? control.selected : control.value.trim());
    const chips = [...group.querySelectorAll('ol-chip')];
    const syncChipSelection = () => chips.forEach((chip) => { chip.selected = chip.dataset.value === currentAnswer(); });

    group.addEventListener('ol-chip-select', (event) => {
        const chip = event.target.closest('ol-chip');
        const value = event.detail.selected ? chip.dataset.value : '';
        if (isPicker) control.selected = value;
        else control.value = value;
        syncChipSelection();
    });
    control.addEventListener(isPicker ? 'ol-options-popover-change' : 'input', syncChipSelection);
    syncChipSelection();
}

/**
 * Check an identifier answer as it's typed: a wrong identifier corrupts record
 * matching silently, so the verdict mirrors the server's normalization.
 * @param {HTMLFormElement} form - a ``[data-id-form]`` whose input carries ``data-id-field``
 * @returns {void}
 */
function initIdentifierForm(form) {
    const input = form.querySelector('[data-id-input]');
    const verdict = form.querySelector('[data-id-verdict]');
    if (!input || !verdict) return;
    const rule = ID_RULES[input.dataset.idField];
    if (!rule) return;

    input.addEventListener('input', () => {
        const raw = input.value.trim();
        if (!raw) {
            verdict.textContent = '';
            verdict.dataset.state = '';
            return;
        }
        const parsed = rule.parse(raw);
        const msg = input.dataset;
        if (rule.isValid(parsed)) {
            verdict.dataset.state = 'ok';
            verdict.textContent = parsed === raw
                ? msg.msgOk
                : msg.msgTidied.replace('__VALUE__', parsed);
        } else {
            verdict.dataset.state = 'bad';
            verdict.textContent = /https?:|\//.test(raw) ? msg.msgUrl : msg.msgBad;
        }
    });
}

/**
 * Drop the "Save and next" receipt from the URL, so a reload doesn't show its toast again.
 * @returns {void}
 */
function clearSavedReceipt() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('saved')) return;
    url.searchParams.delete('saved');
    history.replaceState(history.state, '', url);
}

/**
 * Entry point for the Tasks pages; wires the list, task forms, and done page.
 * @returns {void}
 */
export function init() {
    document.querySelectorAll('[data-contribute-list]').forEach((root) => {
        initTaskList(root);
    });
    document.querySelectorAll('form[data-task-form]').forEach((form) => {
        initSkipButton(form);
        initSiblingSuggestions(form);
    });
    if (document.querySelector('[data-receipt]')) clearSavedReceipt();
    document.querySelectorAll('form[data-id-form]').forEach(initIdentifierForm);
    document.querySelectorAll('[data-contribute-done]').forEach((root) => hideSkippedTasks(root, '[data-same-book]'));
}
