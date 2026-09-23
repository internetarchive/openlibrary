/**
 * First Edits (/contribute) page behavior.
 *
 * Phase 1 saves nothing server-side. Progress within a browser session is a
 * list of task keys in sessionStorage so answered and skipped tasks drop out
 * of the list and the receipt can offer the next open one.
 */

import { parseLccn, isValidLccn, parseOclc, isValidOclc } from './idValidation';

const STORAGE_KEY = 'ol-first-edits-done';

// Same normalization the server applies, so the verdict on screen matches what is stored.
const ID_RULES = {
    lccn: { parse: parseLccn, isValid: isValidLccn },
    oclc_numbers: { parse: parseOclc, isValid: isValidOclc },
};

function readDone() {
    try {
        return new Set(JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]'));
    } catch (e) {
        return new Set();
    }
}

function markDone(key) {
    if (!key) return;
    const done = readDone();
    done.add(key);
    try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...done]));
    } catch (e) {
        // Private mode or blocked storage: the walkthrough still works, just without memory.
    }
}

function initList(root) {
    const done = readDone();
    root.querySelectorAll('[data-task-key]').forEach((el) => {
        if (done.has(el.dataset.taskKey)) el.hidden = true;
    });
    root.querySelectorAll('[data-book-row]').forEach((row) => {
        const open = row.querySelectorAll('[data-task-key]:not([hidden])');
        if (!open.length) row.hidden = true;
    });
    const rows = root.querySelectorAll('[data-book-row]:not([hidden])');
    const empty = root.querySelector('[data-list-empty]');
    if (empty) empty.hidden = rows.length > 0;
}

function initChooser(root) {
    const other = root.querySelector('[data-other-input]');
    const radios = root.querySelectorAll('input[name="choice"]');
    const sync = () => {
        const otherOn = root.querySelector('input[name="choice"][value="other"]:checked');
        if (other) {
            other.hidden = !otherOn;
            if (otherOn) other.querySelector('input')?.focus();
        }
    };
    radios.forEach((r) => r.addEventListener('change', sync));
    sync();

    const form = root.querySelector('form[data-task-form]');
    if (form) {
        form.addEventListener('submit', () => markDone(form.dataset.taskKey));
        const skip = form.querySelector('[data-skip]');
        if (skip) {
            skip.addEventListener('click', () => markDone(form.dataset.taskKey));
        }
    }
}

/**
 * Identifier tasks carry a confirmation the other fields don't need: a wrong
 * identifier corrupts record matching silently, so answers that add one are
 * gated behind an explicit "I opened the record" tick. Answers that add
 * nothing ("different edition", "not sure") are not gated -- saying no has to
 * stay the cheapest thing on the page.
 */
function initIdForm(form) {
    const confirm = form.querySelector('[data-id-confirm]');
    const box = confirm && confirm.querySelector('input[type="checkbox"]');
    const radios = form.querySelectorAll('input[name="choice"]');
    if (!box) return;

    const syncGate = () => {
        const checked = form.querySelector('input[name="choice"]:checked');
        const gated = Boolean(checked && checked.hasAttribute('data-gated'));
        confirm.hidden = !gated;
        box.required = gated;
        if (!gated) box.checked = false;
    };
    radios.forEach((r) => r.addEventListener('change', syncGate));
    syncGate();

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

function initDone(root) {
    markDone(root.dataset.taskKey);
    const done = readDone();
    root.querySelectorAll('[data-task-key]').forEach((el) => {
        if (done.has(el.dataset.taskKey)) el.hidden = true;
    });
    const sameBook = root.querySelector('[data-same-book]');
    if (sameBook && !sameBook.querySelector('[data-task-key]:not([hidden])')) sameBook.hidden = true;
}

export function init() {
    document.querySelectorAll('[data-contribute-list]').forEach(initList);
    document.querySelectorAll('[data-contribute-task]').forEach(initChooser);
    document.querySelectorAll('form[data-id-form]').forEach(initIdForm);
    document.querySelectorAll('[data-contribute-done]').forEach(initDone);
}
