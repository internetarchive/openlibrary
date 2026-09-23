/**
 * First Edits (/contribute) page behavior.
 *
 * Phase 1 saves nothing server-side. Progress within a browser session is a
 * list of task keys in sessionStorage so answered and skipped tasks drop out
 * of the list and the receipt can offer the next open one.
 */

const STORAGE_KEY = 'ol-first-edits-done';

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

    root.querySelectorAll('[data-fill-value]').forEach((chip) => {
        chip.addEventListener('click', () => {
            // A chip that matches an answer already on screen picks that answer.
            const match = (chip.dataset.fillChoices || '').split(' ').filter(Boolean)
                .map((c) => root.querySelector(`input[name="choice"][value="${c}"]`))
                .find(Boolean);
            if (match) {
                match.checked = true;
                sync();
                match.focus();
                return;
            }
            const otherRadio = root.querySelector('input[name="choice"][value="other"]');
            const input = other?.querySelector('input');
            if (otherRadio) otherRadio.checked = true;
            sync();
            if (input) {
                input.value = chip.dataset.fillValue;
                input.focus();
            }
        });
    });

    const form = root.querySelector('form[data-task-form]');
    if (form) {
        form.addEventListener('submit', () => markDone(form.dataset.taskKey));
        const skip = form.querySelector('[data-skip]');
        if (skip) {
            skip.addEventListener('click', () => markDone(form.dataset.taskKey));
        }
    }
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
    document.querySelectorAll('[data-contribute-done]').forEach(initDone);
}
