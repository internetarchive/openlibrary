/**
 * Librarian dashboard (/tasks) page behavior.
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

function readSkipped() {
    try {
        return new Set(JSON.parse(sessionStorage.getItem(SKIPPED_KEY) || '[]'));
    } catch (e) {
        return new Set();
    }
}

function markSkipped(key) {
    const skipped = readSkipped();
    skipped.add(key);
    try {
        sessionStorage.setItem(SKIPPED_KEY, JSON.stringify([...skipped]));
    } catch (e) {
        // Blocked storage: the skipped task just stays listed.
    }
}

/** Hide skipped tasks, then any group (book row, same-book section) left with none. */
function hideSkipped(root, groupSelector) {
    const skipped = readSkipped();
    root.querySelectorAll('[data-task-key]').forEach((el) => {
        if (skipped.has(el.dataset.taskKey)) el.hidden = true;
    });
    root.querySelectorAll(groupSelector).forEach((group) => {
        if (!group.querySelector('[data-task-key]:not([hidden])')) group.hidden = true;
    });
}

function initList(root) {
    hideSkipped(root, '[data-book-row]');
    const empty = root.querySelector('[data-list-empty]');
    if (empty) empty.hidden = !!root.querySelector('[data-book-row]:not([hidden])');
}

function initSkip(form) {
    form.querySelector('[data-skip]')?.addEventListener('click', () => markSkipped(form.dataset.taskKey));
}

/**
 * "Other editions say" chips fill the answer with a sibling's value. The chip
 * matching the current answer shows selected; clicking it again clears it.
 */
function initSuggestions(form) {
    const group = form.querySelector('[data-suggest]');
    const control = form.querySelector('#contrib-other-value');
    if (!group || !control) return;
    const isPicker = control.tagName === 'OL-OPTIONS-POPOVER';
    const current = () => (isPicker ? control.selected : control.value.trim());
    const chips = [...group.querySelectorAll('ol-chip')];
    const sync = () => chips.forEach((chip) => { chip.selected = chip.dataset.value === current(); });

    group.addEventListener('ol-chip-select', (event) => {
        const chip = event.target.closest('ol-chip');
        const value = event.detail.selected ? chip.dataset.value : '';
        if (isPicker) control.selected = value;
        else control.value = value;
        sync();
    });
    control.addEventListener(isPicker ? 'ol-options-popover-change' : 'input', sync);
    sync();
}

/**
 * Identifier tasks check the number as it's typed: a wrong identifier
 * corrupts record matching silently.
 */
function initIdForm(form) {
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

/** Drop the "Save and next" receipt from the URL, so a reload doesn't show its toast again. */
function clearReceipt() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('saved')) return;
    url.searchParams.delete('saved');
    history.replaceState(history.state, '', url);
}

export function init() {
    document.querySelectorAll('[data-contribute-list]').forEach((root) => {
        initList(root);
    });
    document.querySelectorAll('form[data-task-form]').forEach((form) => {
        initSkip(form);
        initSuggestions(form);
    });
    if (document.querySelector('[data-receipt]')) clearReceipt();
    document.querySelectorAll('form[data-id-form]').forEach(initIdForm);
    document.querySelectorAll('[data-contribute-done]').forEach((root) => hideSkipped(root, '[data-same-book]'));
}
